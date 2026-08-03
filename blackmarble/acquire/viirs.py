"""Functions for downloading VIIRS nighttime lights data from NASA LAADS.

On MAAP ADE/DPS, authentication uses the injected MAAP_PGT via maap-py.
Compatible with older maap-py builds that reject cmr_host= / destination_path=.

Local / non-MAAP fallback uses earthaccess (env token or .netrc).
"""

from __future__ import annotations

import inspect
import logging
import os
import warnings
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import rasterio
from rasterio.errors import NotGeoreferencedWarning


logger = logging.getLogger(__name__)


BM_SHORT_NAME = "VNP46A2"
BM_VERSION_EARTHACCESS = "2"
BM_VERSION_CMR = "002"
CMR_GRANULES_UMM = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"

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


def _temporal_str(dt: datetime) -> str:
    return f"{dt:%Y-%m-%d}T00:00:00Z,{dt:%Y-%m-%d}T23:59:59Z"


def _filter_kwargs(fn: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Drop kwargs not accepted by fn (older maap-py is strict)."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return kwargs
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return kwargs
    allowed = set(sig.parameters)
    allowed.discard("self")
    return {k: v for k, v in kwargs.items() if k in allowed}


def _call_search_granule(maap: Any, **kwargs: Any) -> list[Any]:
    """Call searchGranule with only kwargs supported by the installed maap-py."""
    fn = maap.searchGranule
    filtered = _filter_kwargs(fn, kwargs)
    dropped = sorted(set(kwargs) - set(filtered))
    if dropped:
        logger.warning("maap.searchGranule ignoring unsupported kwargs: %s", dropped)
    return fn(**filtered)


def _maap_download_url(maap: Any, url: str, output_dir: Path) -> Path:
    """Download one HTTPS URL via maap.downloadGranule across API variants."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fn = maap.downloadGranule

    # 1) Keyword forms used by various maap-py versions
    for key in ("destination_path", "destpath", "dest_path", "outdir"):
        try:
            result = fn(url, **{key: str(output_dir)})
            return Path(result)
        except TypeError:
            continue

    # 2) Positional destination (common older style)
    try:
        result = fn(url, str(output_dir))
        return Path(result)
    except TypeError:
        pass

    # 3) URL-only API: chdir into output_dir then download
    prev = Path.cwd()
    try:
        os.chdir(output_dir)
        result = fn(url)
        path = Path(result)
        if not path.is_absolute():
            path = output_dir / path
        return path
    finally:
        os.chdir(prev)


def _https_url_from_umm_item(item: dict[str, Any]) -> str | None:
    related = (item.get("umm") or {}).get("RelatedUrls") or []
    https_candidates: list[str] = []
    for entry in related:
        if not isinstance(entry, dict):
            continue
        url = entry.get("URL")
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        utype = str(entry.get("Type", "")).upper()
        if "GET DATA" in utype:
            return url
        https_candidates.append(url)
    return https_candidates[0] if https_candidates else None


def _download_via_maap_search(
    maap: Any, dt: datetime, bbox: tuple[float, float, float, float], output_dir: Path
) -> list[Path]:
    temporal = _temporal_str(dt)
    bbox_csv = _bbox_str(bbox)

    results: list[Any] = []
    for version in (BM_VERSION_CMR, BM_VERSION_EARTHACCESS):
        logger.info(
            "Searching VIIRS via maap.searchGranule short_name=%s version=%s",
            BM_SHORT_NAME,
            version,
        )
        results = _call_search_granule(
            maap,
            short_name=BM_SHORT_NAME,
            version=version,
            temporal=temporal,
            bounding_box=bbox_csv,
            limit=100,
            cmr_host="cmr.earthdata.nasa.gov",
        )
        if results:
            break

    if not results:
        raise RuntimeError(
            f"No {BM_SHORT_NAME} granules from maap.searchGranule for "
            f"date={dt:%Y-%m-%d} bbox={bbox_csv}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %d VIIRS granule(s) via granule.getData...", len(results))

    filelist: list[Path] = []
    for granule in results:
        # getData(destpath=...) on modern; positional on some builds
        path: Path | None = None
        try:
            path = Path(granule.getData(str(output_dir)))
        except TypeError:
            try:
                path = Path(granule.getData(destpath=str(output_dir)))
            except TypeError:
                prev = Path.cwd()
                try:
                    os.chdir(output_dir)
                    path = Path(granule.getData())
                    if not path.is_absolute():
                        path = output_dir / path
                finally:
                    os.chdir(prev)
        if path is not None and path.exists():
            filelist.append(path)

    if not filelist:
        raise RuntimeError("maap.searchGranule succeeded but no files were downloaded")
    return filelist


def _download_via_cmr_umm_and_maap(
    maap: Any, dt: datetime, bbox: tuple[float, float, float, float], output_dir: Path
) -> list[Path]:
    """Direct NASA CMR search + maap.downloadGranule (uses MAAP_PGT on DPS)."""
    import requests

    bbox_csv = _bbox_str(bbox)
    temporal = _temporal_str(dt)
    items: list[dict[str, Any]] = []

    for version in (BM_VERSION_CMR, BM_VERSION_EARTHACCESS):
        params = {
            "short_name": BM_SHORT_NAME,
            "version": version,
            "temporal": temporal,
            "bounding_box": bbox_csv,
            "page_size": "100",
        }
        logger.info("Searching VIIRS via CMR UMM-JSON version=%s", version)
        resp = requests.get(CMR_GRANULES_UMM, params=params, timeout=120)
        resp.raise_for_status()
        items = list(resp.json().get("items") or [])
        if items:
            break

    if not items:
        raise RuntimeError(
            f"No {BM_SHORT_NAME} granules from CMR UMM-JSON for "
            f"date={dt:%Y-%m-%d} bbox={bbox_csv}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    filelist: list[Path] = []

    for item in items:
        url = _https_url_from_umm_item(item)
        if not url:
            logger.warning("Skipping granule with no HTTPS URL: %s", item.get("meta"))
            continue
        logger.info("Downloading via maap.downloadGranule: %s", url)
        local = _maap_download_url(maap, url, output_dir)
        if local.exists():
            filelist.append(local)

    if not filelist:
        raise RuntimeError("CMR UMM search succeeded but no files were downloaded")
    return filelist


def _download_via_maap(
    dt: datetime, bbox: tuple[float, float, float, float], output_dir: Path
) -> list[Path]:
    from maap.maap import MAAP

    maap = MAAP()

    try:
        return _download_via_maap_search(maap, dt, bbox, output_dir)
    except Exception as search_exc:  # noqa: BLE001
        logger.warning(
            "maap.searchGranule/getData path failed (%s); trying CMR UMM + downloadGranule",
            search_exc,
        )
        return _download_via_cmr_umm_and_maap(maap, dt, bbox, output_dir)


def _download_via_earthaccess(
    dt: datetime, bbox: tuple[float, float, float, float], output_dir: Path
) -> list[Path]:
    import earthaccess

    logger.info("Logging in to Earthdata via earthaccess (local fallback)...")
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
    """Search and download VIIRS VNP46A2 for a date/bbox. Prefer maap-py on DPS."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filelist: list[Path] | None = None
    maap_error: Exception | None = None

    try:
        filelist = _download_via_maap(dt, bbox, output_dir)
        logger.info("VIIRS download completed via maap-py (%d file(s))", len(filelist))
    except ImportError:
        logger.info("maap-py not installed; using earthaccess fallback")
    except Exception as exc:  # noqa: BLE001
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
