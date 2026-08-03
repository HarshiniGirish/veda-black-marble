"""Functions for downloading VIIRS nighttime lights data from NASA LAADS.

On MAAP ADE/DPS, authentication uses the injected MAAP_PGT via maap-py
(same pattern as OPERA / GEDI DPS algorithms). No Earthdata token CLI arg
or manual EARTHDATA_TOKEN export is required.

Local / non-MAAP fallback uses earthaccess (env token or .netrc).
"""

from __future__ import annotations

import logging
import warnings
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import rasterio
from rasterio.errors import NotGeoreferencedWarning


logger = logging.getLogger(__name__)


BM_SHORT_NAME = "VNP46A2"
# earthaccess accepts "2"; CMR/maap-py typically wants "002"
BM_VERSION_EARTHACCESS = "2"
BM_VERSION_CMR = "002"

NTL_DATASET_PATH = (
    "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data_Fields/Gap_Filled_DNB_BRDF-Corrected_NTL"
)


def convert_to_tiff(
    input_h5: str | Path, output_path: str | Path, dataset_path: str = NTL_DATASET_PATH
) -> Path:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        subdatasets = rasterio.open(input_h5).subdatasets
    dnb_sds = [sds for sds in subdatasets if dataset_path in sds][0]

    with rasterio.open(dnb_sds, "r") as src:
        profile = src.profile
        data = src.read(1)

    dst_profile = deepcopy(profile)
    dst_profile.update(
        driver="GTiff", predictor=3, compress="deflate", blockxsize=256, blockysize=256
    )
    with rasterio.open(output_path, mode="w", **dst_profile) as dst:
        dst.write(data, 1)

    return Path(output_path)


def _bbox_str(bbox: tuple[float, float, float, float]) -> str:
    return ",".join(str(v) for v in bbox)


def _download_via_maap(
    dt: datetime, bbox: tuple[float, float, float, float], output_dir: Path
) -> list[Path]:
    """Search/download VNP46A2 using maap-py (MAAP_PGT). Raises if unavailable."""
    from maap.maap import MAAP

    maap = MAAP()
    temporal = f"{dt:%Y-%m-%d}T00:00:00Z,{dt:%Y-%m-%d}T23:59:59Z"
    bbox_csv = _bbox_str(bbox)

    logger.info("Searching VIIRS via maap-py (MAAP auth)...")
    results = maap.searchGranule(
        cmr_host="cmr.earthdata.nasa.gov",
        short_name=BM_SHORT_NAME,
        version=BM_VERSION_CMR,
        temporal=temporal,
        bounding_box=bbox_csv,
        limit=100,
    )

    if not results:
        # Some CMR records use version "2" instead of "002"
        results = maap.searchGranule(
            cmr_host="cmr.earthdata.nasa.gov",
            short_name=BM_SHORT_NAME,
            version=BM_VERSION_EARTHACCESS,
            temporal=temporal,
            bounding_box=bbox_csv,
            limit=100,
        )

    if not results:
        raise RuntimeError(
            f"No {BM_SHORT_NAME} granules found via maap-py for "
            f"date={dt:%Y-%m-%d} bbox={bbox_csv}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %d VIIRS granule(s) via maap-py getData...", len(results))

    filelist: list[Path] = []
    for granule in results:
        path = Path(granule.getData(str(output_dir)))
        if path.suffix.lower() in {".h5", ".hdf", ".hdf5"} or path.exists():
            filelist.append(path)

    if not filelist:
        raise RuntimeError("maap-py search succeeded but no files were downloaded")

    return filelist


def _download_via_earthaccess(
    dt: datetime, bbox: tuple[float, float, float, float], output_dir: Path
) -> list[Path]:
    """Local / non-MAAP fallback using earthaccess."""
    import earthaccess

    logger.info("Logging in to Earthdata via earthaccess (local fallback)...")
    # Prefer env/.netrc; never prompt in DPS/non-interactive shells
    auth = earthaccess.login(strategy="environment")
    if not auth:
        auth = earthaccess.login(strategy="netrc")
    if not auth:
        raise RuntimeError(
            "earthaccess login failed. On MAAP DPS use maap-py (MAAP_PGT). "
            "Locally set EARTHDATA_TOKEN or configure ~/.netrc."
        )

    logger.info("Searching for VIIRS data via earthaccess...")
    results = earthaccess.search_data(
        short_name=BM_SHORT_NAME,
        version=BM_VERSION_EARTHACCESS,
        temporal=(dt.strftime("%Y-%m-%d"), dt.strftime("%Y-%m-%dT23:59:59"), True),
        bounding_box=bbox,
    )
    if not results:
        raise RuntimeError(
            f"No {BM_SHORT_NAME} granules found via earthaccess for date={dt:%Y-%m-%d}"
        )

    logger.info("Downloading VIIRS data via earthaccess...")
    downloaded = earthaccess.download(
        results, local_path=output_dir, show_progress=False
    )
    return [Path(p) for p in downloaded]


def download_viirs(
    dt: datetime, bbox: tuple[float, float, float, float], output_dir: str | Path
) -> dict[str, list[Path]]:
    """Search and download VIIRS VNP46A2 files for a given date and bounding box.

    Prefer maap-py when available (ADE/DPS). Fall back to earthaccess locally.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filelist: list[Path] | None = None
    maap_error: Exception | None = None

    try:
        filelist = _download_via_maap(dt, bbox, output_dir)
        logger.info("VIIRS download completed via maap-py (%d file(s))", len(filelist))
    except ImportError:
        logger.info("maap-py not installed; using earthaccess fallback")
    except Exception as exc:  # noqa: BLE001 — fall back for any MAAP/CMR failure
        maap_error = exc
        logger.warning("maap-py VIIRS download failed (%s); trying earthaccess", exc)

    if filelist is None:
        try:
            filelist = _download_via_earthaccess(dt, bbox, output_dir)
        except Exception as exc:
            if maap_error is not None:
                raise RuntimeError(
                    f"VIIRS download failed via maap-py ({maap_error}) "
                    f"and earthaccess ({exc})"
                ) from exc
            raise

    tiff_filelist = [convert_to_tiff(f, f.with_suffix(".tif")) for f in filelist]
    return {"gap_filled_ntl": tiff_filelist}
