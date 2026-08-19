"""依赖哈希生成工具。

下载指定版本的 wheel 并计算 SHA256 哈希，输出可直接写入 requirements.txt 的格式。
用于跨平台部署时为当前平台生成哈希值。

重要: 本工具生成的是【当前运行平台】的哈希。不同平台（macOS/Windows/Linux）
的 wheel 文件不同，哈希也不同。pip 的 --require-hashes 会自动匹配当前平台
对应的哈希，因此 requirements.txt 中可以同时包含多个平台的哈希。

用法:
    python scripts/generate_hashes.py              # 为当前平台生成哈希
    python scripts/generate_hashes.py --output requirements.txt  # 直接写入文件
    python scripts/generate_hashes.py --packages pandas==3.0.1 numpy==2.4.3
"""

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path


DEFAULT_PACKAGES = [
    "pandas==3.0.1",
    "numpy==2.4.3",
    "openpyxl==3.1.5",
    "xlrd==2.0.1",
]


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_hash_output(output: str) -> dict:
    """解析 generate_hashes 的输出，返回 {包名: [哈希行列表]}。"""
    result = {}
    current_pkg = None
    for line in output.split('\n'):
        stripped = line.strip()
        if '==' in stripped and not stripped.startswith('--hash'):
            current_pkg = stripped.split('==')[0].strip()
            result[current_pkg] = []
        elif stripped.startswith('--hash') and current_pkg:
            result[current_pkg].append(stripped)
    return result


def generate_hashes(packages: list[str]) -> str:
    lines = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for pkg_spec in packages:
            print(f"Downloading {pkg_spec}...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "download", pkg_spec,
                 "-d", tmpdir, "--no-deps", "--timeout", "120"],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                print(f"  ERROR: Failed to download {pkg_spec}", file=sys.stderr)
                print(f"  {result.stderr}", file=sys.stderr)
                continue

            # Find the downloaded file
            pkg_name = pkg_spec.split("==")[0].lower().replace("-", "_")
            downloaded = None
            for f in Path(tmpdir).iterdir():
                if f.is_file() and f.name.lower().startswith(pkg_name):
                    downloaded = f
                    break

            if downloaded is None:
                print(f"  ERROR: Could not find downloaded file for {pkg_spec}", file=sys.stderr)
                continue

            hash_val = sha256_of_file(downloaded)
            line = f"{pkg_spec} \\\n    --hash=sha256:{hash_val}"
            lines.append(line)
            print(f"  {pkg_spec} -> sha256:{hash_val}")

            # Clean up to avoid confusion with next package
            downloaded.unlink()

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="生成依赖包的 SHA256 哈希")
    parser.add_argument(
        "--packages", nargs="+", default=None,
        help="指定包列表，如: pandas==3.0.1 numpy==2.4.3",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="输出到文件（默认输出到终端）",
    )
    args = parser.parse_args()

    packages = args.packages or DEFAULT_PACKAGES
    output = generate_hashes(packages)

    if args.output:
        # 追加模式：将当前平台的哈希合并到已有 requirements.txt
        output_path = Path(args.output)
        if output_path.exists():
            existing = output_path.read_text(encoding='utf-8')
            # 解析新生成的哈希：{包名: [哈希行列表]}
            new_hashes = _parse_hash_output(output)
            # 对每个包，将新哈希追加到已有行的末尾
            lines = existing.split('\n')
            updated_lines = []
            for line in lines:
                stripped = line.strip()
                if '==' in stripped and '--hash=' in stripped:
                    pkg_name = stripped.split('==')[0].strip()
                    if pkg_name in new_hashes:
                        # 提取该包已有的哈希集合
                        existing_hashes = set(re.findall(r'sha256:[a-f0-9]+', line))
                        # 追加尚未存在的新哈希
                        for new_hash_line in new_hashes[pkg_name]:
                            for h in re.findall(r'sha256:[a-f0-9]+', new_hash_line):
                                if h not in existing_hashes:
                                    line += f' \\\n    --hash={h}'
                                    existing_hashes.add(h)
                updated_lines.append(line)
            output_path.write_text('\n'.join(updated_lines) + "\n", encoding="utf-8")
            print(f"\nHashes merged into {args.output}")
        else:
            output_path.write_text(output + "\n", encoding="utf-8")
            print(f"\nHashes written to {args.output}")
    else:
        print("\n" + "=" * 60)
        print("将以下内容追加到 requirements.txt 对应包的 --hash 行中:")
        print("(pip 会自动匹配当前平台的哈希，忽略其他平台的)")
        print("=" * 60)
        print(output)


if __name__ == "__main__":
    main()
