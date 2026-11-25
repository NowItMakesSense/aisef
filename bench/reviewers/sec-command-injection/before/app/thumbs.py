import subprocess


def make_thumbnail(src: str, dst: str) -> None:
    subprocess.run(["convert", src, "-resize", "200x200", dst], check=True)
