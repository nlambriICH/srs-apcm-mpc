"""Build the pseudonymised student dataset.

Reads the original files from private/ (gitignored) and writes:
  private/pseudonymised/srs_gpr_raw.xlsx     raw tables (HyperArc beams, portal dosimetry, complexity, MPC)
  private/pseudonymised/srs_gpr_clean.xlsx   cleaned, merged dataset (3%/1 mm gamma)
  private/id_mapping.xlsx                    real -> pseudonym tables (reused so codes stay stable)

The pseudonymised files are NOT encrypted: do not upload them. Encrypt them into release/ with
tools/encrypt_data.py and share only the zips.

Usage:  python tools/pseudonymise.py
"""

from __future__ import annotations

import json
import re
import secrets
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "private"
PSEUDO = PRIVATE / "pseudonymised"  # unencrypted outputs: never share these directly
RAW_IN = PRIVATE / "RawData.xlsx"
CLEAN_IN = PRIVATE / "dataset_3p1mm_final.xlsx"
MAPPING = PRIVATE / "id_mapping.xlsx"

RAW_OUT = PSEUDO / "srs_gpr_raw.xlsx"
CLEAN_OUT = PSEUDO / "srs_gpr_clean.xlsx"

# Real machine/institution names and leak-check patterns are identifying, so they live in private/
CONFIG = json.loads((PRIVATE / "pseudonymise_config.json").read_text(encoding="utf-8"))
MACHINES = CONFIG["machines"]  # real name -> pseudonym
INSTITUTIONS = CONFIG["institutions"]  # real name -> pseudonym
FORBIDDEN = re.compile("|".join(CONFIG["forbidden_patterns"]), re.I)  # must not appear in outputs

# Target-count columns from the export script, replaced by the manual NumberOfLesions
TARGET_COUNT_COLS = [
    "NumberOfTargetVolumeParts",
    "NumberOfDisjointTargets",
    "DoseLevel",
    "NumberOfTargetsFromDoseLevel",
]
# Derived from a timestamp; students can re-derive them
DERIVED_TIME_COLS = ["Year", "Month", "Weekday", "Hour", "cal_year"]

# Raw complexity names -> names used in the paper / cleaned dataset
COMPLEXITY_RENAME = {
    "MUOverDosePerFraction": "MU/DoseFx",
    "meanMLCSpeed": "MeanMLCSpeed",
    "meanRR": "MeanDoseRate",
    "RRmodulation": "DoseRateModulation",
    "meanGS": "MeanGantrySpeed",
    "GSmodulation": "GantrySpeedModulation",
    "Q1 MLCGap": "Q1MLCGap",
    "Median MLCGap": "MedianMLCGap",
    "PI": "BI",
    "PM": "BM",
}


def build_map(values, prefix: str, width: int, existing: dict | None = None) -> dict:
    """Map each distinct value to PREFIX0001..., in random order. Keeps existing codes."""
    mapping = dict(existing or {})
    used = {int(v[len(prefix):]) for v in mapping.values()}
    new = [v for v in pd.unique(pd.Series(list(values)).dropna()) if v not in mapping]
    order = list(range(len(new)))
    secrets.SystemRandom().shuffle(order)
    next_free = (n for n in range(1, 10**width) if n not in used)
    codes = [next(next_free) for _ in new]
    for i, v in zip(order, new):
        mapping[v] = f"{prefix}{codes[i]:0{width}d}"
    return mapping


def load_existing_maps() -> dict[str, dict]:
    if not MAPPING.exists():
        return {}
    sheets = pd.read_excel(MAPPING, sheet_name=None, dtype=str)
    return {name: dict(zip(df["original"], df["pseudonym"])) for name, df in sheets.items()}


def main() -> None:
    PSEUDO.mkdir(exist_ok=True)
    print("Reading originals...")
    raw = pd.read_excel(RAW_IN, sheet_name=["BeamInfoHyperArc", "PDInfo", "BeamComplexity", "MPC"])
    ha, pdi, bc, mpc = (raw[k] for k in ["BeamInfoHyperArc", "PDInfo", "BeamComplexity", "MPC"])
    clean = pd.read_excel(CLEAN_IN).copy()

    # The cleaned file has a hashed ID; recover the real one from the DICOM path to link both files
    clean_real_pid = clean["DicomFile"].str.extract(r"Dicoms[^0-9]+([0-9]+)")[0]
    assert clean_real_pid.notna().all(), "Could not recover PatientID from DicomFile"
    clean["PatientID"] = clean_real_pid.astype("int64")

    # Data minimisation: keep only HyperArc patients in every table
    hyperarc_pids = set(ha["PatientID"])
    pdi = pdi[pdi["PatientID"].isin(hyperarc_pids)].copy()
    bc = bc[bc["PatientID"].isin(hyperarc_pids)].copy()

    # ---- NumberOfLesions (manual, from the cleaned dataset) ----
    lesions = (
        clean.groupby(["PatientID", "Course", "Plan"])["NumberOfLesions"].first().rename("NumberOfLesions")
    )
    ha = ha.merge(lesions, left_on=["PatientID", "Course", "Plan"], right_index=True, how="left")
    # The cleaned file holds only multi-lesion plans: any plan not in it is single-lesion
    ha["NumberOfLesions"] = ha["NumberOfLesions"].fillna(1).astype("int64")
    ha = ha.drop(columns=TARGET_COUNT_COLS)

    # ---- Build / reuse mappings ----
    maps = load_existing_maps()
    pid_key = lambda s: s.astype("int64").astype(str)
    maps["PatientID"] = build_map(pid_key(ha["PatientID"]), "P", 4, maps.get("PatientID"))
    maps["Course"] = build_map(ha["Course"].astype(str), "C", 4, maps.get("Course"))
    maps["PDImageUID"] = build_map(
        pd.concat([pdi["PDImageUID"], clean["PDImageUID"]]).astype(str), "IMG", 5, maps.get("PDImageUID")
    )
    maps["CreationUserName"] = build_map(
        pd.concat([ha["CreationUserName"], clean["CreationUserName"]]), "U", 2, maps.get("CreationUserName")
    )

    def pseudo_pid(df):
        df["PatientID"] = pid_key(df["PatientID"]).map(maps["PatientID"])
        assert df["PatientID"].notna().all()

    def pseudo_common(df):
        for col in ["MachineName", "MachineName_y"]:
            if col in df:
                assert df[col].isin(MACHINES).all(), f"unknown machine in {col}"
                df[col] = df[col].map(MACHINES)
        if "Institution" in df:
            df["Institution"] = df["Institution"].map(INSTITUTIONS)
        if "CreationUserName" in df:
            df["CreationUserName"] = df["CreationUserName"].map(maps["CreationUserName"])
        if "PDImageUID" in df:
            df["PDImageUID"] = df["PDImageUID"].astype(str).map(maps["PDImageUID"])
        return df.drop(columns=[c for c in ["DicomFile"] if c in df])

    # ---- Raw tables ----
    pseudo_pid(ha)
    ha["Course"] = ha["Course"].astype(str).map(maps["Course"])
    ha = pseudo_common(ha)

    pseudo_pid(pdi)  # PD Course/Plan are QA names (e.g. "QA/B"): kept as they are
    pdi = pseudo_common(pdi)

    pseudo_pid(bc)
    bc = pseudo_common(bc.rename(columns=COMPLEXITY_RENAME))

    mpc = pseudo_common(mpc.copy())

    # ---- Cleaned dataset ----
    clean = clean.drop(columns=["PatientIDAnonym"] + TARGET_COUNT_COLS + DERIVED_TIME_COLS)
    pseudo_pid(clean)
    unknown_courses = set(clean["Course"].astype(str)) - set(maps["Course"])
    assert not unknown_courses, unknown_courses
    clean["Course"] = clean["Course"].astype(str).map(maps["Course"])
    clean = pseudo_common(clean)
    clean = clean[["PatientID"] + [c for c in clean.columns if c != "PatientID"]]

    # ---- Leak check ----
    real_pids = {str(int(p)) for p in hyperarc_pids}
    real_courses = {c for c in maps["Course"] if re.search(r"\d{4,}", c)}  # dates / encounter numbers
    tables = {"BeamInfoHyperArc": ha, "PDInfo": pdi, "BeamComplexity": bc, "MPC": mpc, "clean": clean}
    for name, df in tables.items():
        for col in df.columns:
            s = df[col].dropna()
            if s.dtype == object or str(s.dtype).startswith("str"):
                txt = s.astype(str)
                hits = txt[txt.str.contains(FORBIDDEN)]
                assert hits.empty, f"{name}.{col} leaks: {hits.head().tolist()}"
                toks = set(re.findall(r"\d{5,}", " ".join(txt.unique())))
                assert not (toks & real_pids), f"{name}.{col} contains a real PatientID"
                assert not (set(txt) & real_courses), f"{name}.{col} contains a real Course"
            elif pd.api.types.is_integer_dtype(s):
                assert not set(s.astype(str)) & real_pids, f"{name}.{col} contains a real PatientID"
    print("Leak check passed.")

    # ---- Write outputs ----
    with pd.ExcelWriter(RAW_OUT) as w:
        ha.to_excel(w, sheet_name="BeamInfoHyperArc", index=False)
        pdi.to_excel(w, sheet_name="PDInfo", index=False)
        bc.to_excel(w, sheet_name="BeamComplexity", index=False)
        mpc.to_excel(w, sheet_name="MPC", index=False)
    clean.to_excel(CLEAN_OUT, index=False)

    with pd.ExcelWriter(MAPPING) as w:
        for name, m in maps.items():
            pd.DataFrame({"original": list(m), "pseudonym": list(m.values())}).to_excel(
                w, sheet_name=name, index=False
            )

    for name, df in tables.items():
        print(f"  {name:17} {df.shape}")
    print(f"NumberOfLesions in raw: {ha['NumberOfLesions'].value_counts().sort_index().to_dict()}")
    print(f"Wrote {RAW_OUT.name}, {CLEAN_OUT.name} -> {PSEUDO} (unencrypted, do not share)")
    print("Next: python tools/encrypt_data.py private/pseudonymised/srs_gpr_raw.xlsx -o release/srs_gpr_data.zip")


if __name__ == "__main__":
    main()
