import glob
from pathlib import Path


def read_edid_name(connector_name):
    for path in glob.glob(f"/sys/class/drm/card*-{connector_name}/edid"):
        try:
            data = Path(path).read_bytes()
            if len(data) < 128:
                continue
            for offset in range(54, 126, 18):
                tag = data[offset + 3]
                if tag != 0xFC:
                    continue
                raw = data[offset + 5 : offset + 18]
                name = raw.split(b"\n")[0].rstrip(b" ").decode("ascii", errors="replace").strip()
                if name:
                    return name
        except Exception:
            continue
    return None
