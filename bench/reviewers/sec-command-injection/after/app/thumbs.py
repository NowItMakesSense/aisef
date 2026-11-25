import subprocess


def make_thumbnail(src: str, dst: str, size: str = "200x200") -> None:
    """`size` agora vem do formulario de upload."""
    subprocess.run("convert %s -resize %s %s" % (src, size, dst), shell=True, check=True)
