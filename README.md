# Predicting VMAT gamma passing rates in multi-target SRS

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/nlambriICH/srs-apcm-mpc/blob/main/notebooks/gpr_prediction.ipynb)

A hands-on data science project with real (pseudonymised) clinical radiotherapy data.

**Goal:** predict the **gamma passing rate (GPR)** of each VMAT arc from

1. **arc-specific plan complexity metrics (aPCMs)**, which describe how hard an arc is to deliver, and
2. **daily Machine Performance Check (MPC)** results of the linac that delivered the arc.

The plans are **single-isocenter multi-target stereotactic radiosurgery (SIMT-SRS)** plans for brain
lesions, made with Varian HyperArc. Every arc was checked before treatment with **Varian Portal
Dosimetry**: the arc is delivered onto the electronic portal imager (EPID), and the measured image is
compared with the predicted image using a gamma analysis. The GPR is the percentage of points that pass.

---

## Quick start (Google Colab)

1. Click the **Open in Colab** button above. It opens
   [`notebooks/gpr_prediction.ipynb`](notebooks/gpr_prediction.ipynb) in Google Colab.
   Use *File → Save a copy in Drive* to keep your work.
2. Run the first cells. They download the encrypted archive `srs_gpr_data.zip` from Google Drive.
3. Type the **passkey** you get during the lecture when the notebook asks for it.
4. Work through the notebook sections: explore → merge → clean → analyse → model.

To work locally instead: `pip install -r requirements.txt`, put `srs_gpr_data.zip` next to the
notebook, and run Jupyter.

### Data use rules

- The data are **pseudonymised**: patients, courses, planners and images are labelled with codes
  (`P0001`, `C0001`, `U01`, `IMG00001`), and institution and machines with generic names.
- Use the data **only for this course**. Do not share the archive or the passkey, and do not upload
  the data to other services.

---

## Data files

The archive `srs_gpr_data.zip` contains **`srs_gpr_raw.xlsx`**: four raw tables exported from the
clinical systems. You must merge and clean them yourself.

### `srs_gpr_raw.xlsx`: sheets and how they connect

```
BeamInfoHyperArc ──(PatientID, Plan, Beam ↔ Field)────────────► BeamComplexity
       │
       └──(PatientID, PDPlan ↔ Plan, Beam ↔ PDBeam)───────────► PDInfo
                                                                   │
                         (MachineName, date of SessionDateTime ↔ date of Date)
                                                                   ▼
                                                                  MPC
```

| Sheet | Rows | One row is… |
|---|---|---|
| `BeamInfoHyperArc` | 4,670 | a treatment arc of a HyperArc plan (plan settings and prescription) |
| `PDInfo` | 11,892 | a portal dosimetry analysis of a verification arc (gamma result) |
| `BeamComplexity` | 4,668 | a treatment arc (complexity metrics computed from the DICOM RT Plan with PlanAnalyzer) |
| `MPC` | 3,420 | one MPC run on one linac |

Things to expect in the raw data (finding and fixing them is part of the exercise):

- Not every plan is a multi-target SRS plan, and not every arc has a portal dosimetry result.
- An arc can have **several** portal dosimetry analyses: repeated measurements, and different gamma criteria
  (3%, 2%, 1% dose difference). The study used **3% / 1 mm** with a 20% threshold.
- Key columns do not always match exactly (upper/lower case, arc names like `Field 1` vs `arc1`, mixed types).
- Units and formats differ between tables (GPR as a fraction vs a percentage, dose as `"24.000 Gy"` vs `24`,
  dates as text).
- MPC can run several times per day and some tests are missing on some days.

---

## Column dictionary

### `BeamInfoHyperArc` (from the treatment planning system)

| Column | Description |
|---|---|
| `PatientID` | Pseudonymised patient code (`P0001`…). A patient can have several courses, plans and arcs. |
| `Course` | Pseudonymised treatment course (`C0001`…). |
| `Plan` | Treatment plan name (free text in Italian, typed by the planner, e.g. `RC_8_lesioni` = radiosurgery, 8 lesions). |
| `PDCourse`, `PDPlan` | Course and plan of the **verification (QA) plan** used for portal dosimetry. Empty if no QA plan was found. Link to `PDInfo`. |
| `Beam` | Arc name within the plan (`Field 1`, `arc1`, …). |
| `BeamTechnique` | `ARC` or `SRS ARC` (high-dose-rate SRS delivery mode). |
| `MachineName` | Linac: `LINAC_EDGE` (Varian Edge) or `LINAC_TB` (Varian TrueBeam STx). |
| `Energy` | Photon beam energy. `FFF` = flattening-filter-free. |
| `MLC`, `MLCType` | Multileaf collimator model (Varian HD120, 2.5 mm central leaves) and delivery type. |
| `DosimetricLeafGap` | Dosimetric leaf gap (cm), a beam-model parameter of the planning system. |
| `MLCTransmissionFactor` | MLC transmission (fraction), a beam-model parameter. |
| `OptAlgo` | Optimisation algorithm and version (Photon Optimizer). |
| `ApertureShapeController` | Eclipse setting that penalises complex MLC apertures (`Off` … `Very High`). |
| `DoseAlgo` | Dose calculation algorithm and version (Acuros XB or AAA; the spelling is inconsistent). |
| `GridSize` | Dose calculation grid size (cm). |
| `IsHyperArc` | Whether the plan was created with HyperArc. |
| `DiagnosisCode`, `DiagnosisCodeTable` | Diagnosis code(s) and coding system (ICD-9), e.g. 198.3 = brain metastases, 191.x = brain tumour, 225.x = meningioma. |
| `DosePerFraction` | Prescribed dose per fraction (text with unit). |
| `NumberOfFractions` | Number of treatment sessions. |
| `TargetVolumeID` | Name of the prescription target structure (free text). |
| `ApprovalStatus` | Plan status in the record-and-verify system. |
| `CreationUserName` | Pseudonymised planner (`U01`…). |
| `CreationDateTime` | Plan creation date and time. |
| `NumberOfLesions` | Number of lesions treated by the plan, **counted manually** (1 = single-lesion plan). |

### `PDInfo` (portal dosimetry results)

| Column | Description |
|---|---|
| `PatientID` | Pseudonymised patient code. |
| `Course`, `Plan`, `PDCourse`, `PDPlan` | Verification (QA) course and plan. In this sheet `Course = PDCourse` and `Plan = PDPlan`. |
| `PDBeam` | Arc name in the QA plan (matches `Beam`). |
| `PDImage` | Label of the measured portal image. |
| `PDImageUID` | Pseudonymised image identifier (`IMG00001`…). |
| `SessionDateTime` | Date and time of the measurement session. Use it to match the MPC of the same day. |
| `AnalysisMode` | `CU` = images in calibrated units (EPID dose calibration). |
| `NormalizationMethod` | Image normalisation used in the analysis. |
| `GammaParamDoseDiff` | Gamma dose-difference criterion (0.03 = 3%). |
| `GammaParamDTA` | Gamma distance-to-agreement criterion (mm). |
| `Threshold` | Low-dose threshold: points below this fraction of the maximum are excluded (0.2 = 20%). |
| `GPR` | **Target.** Gamma passing rate, here as a **fraction** (0–1). |
| `XSizeRefImage`, `YSizeRefImage` | Size of the predicted (reference) image in pixels. |
| `XResRefImage`, `YResRefImage` | Pixel size of the predicted image (mm). |
| `XSizeMeasImage`, `YSizeMeasImage`, `XResMeasImage`, `YResMeasImage` | The same for the measured image. |
| `MinDoseValueRefImg`, `MaxDoseValueRefImg` | Minimum and maximum of the predicted image (CU). |
| `MinDoseValueMeasImg`, `MaxDoseValueMeasImg` | Minimum and maximum of the measured image (CU). |

### `BeamComplexity` (arc-specific plan complexity metrics, aPCMs)

Computed from the DICOM RT Plan with the **PlanAnalyzer** software. Metrics marked "MU-weighted" are
averaged over the control points of the arc, weighted by the MU delivered at each control point.

| Column | Unit | Description |
|---|---|---|
| `Institution`, `TPSmanufacturer`, `TPSmodel` | – | Metadata (constant). |
| `PatientID` | – | Pseudonymised patient code. |
| `Plan`, `PlanDate` | – | Plan name and plan date. |
| `MachineManufacturer`, `MachineModel`, `MachineName` | – | Linac metadata (`TDS` = TrueBeam delivery system). |
| `numleaves`, `minleafwidth` | –, mm | Number of MLC leaf pairs considered and narrowest leaf width. |
| `Field` | – | Arc name (matches `Beam` in `BeamInfoHyperArc`). |
| `subtype`, `subsubtype` | – | Beam type (`Arc`, `VMAT`). |
| `Energy` | MV | Nominal energy. |
| `MU` | MU | Monitor units of the arc. |
| `DosePerFraction` | Gy | Prescribed dose per fraction. |
| `MU/DoseFx` | MU Gy⁻¹ | Monitor units normalised by the dose per fraction. |
| `beam-on time` | s | Estimated delivery time of the arc. |
| `iso` | mm | Isocentre coordinates (x y z) in a single text field. |
| `couch`, `coll` | deg | Couch and collimator angles. |
| `FX`, `FY` | mm | Jaw field size in X and Y. The maximum beam area defined by the jaws is `FX × FY / 100` (cm²). |
| `Xtracking`, `Ytracking` | – | Whether jaw tracking was used in X / Y. |
| `lowerleaf`, `upperleaf` | – | Index of the first and last MLC leaf pair inside the field. |
| `Arclength` | deg | Gantry rotation of the arc. |
| `MeanMLCSpeed` | cm s⁻¹ | Mean speed of the in-field leaves. |
| `MLCSpeedModulation` | cm s⁻¹ mm⁻¹ | Leaf speed variation divided by the total leaf travel. |
| `MeanDoseRate` | MU min⁻¹ | Mean dose rate. |
| `DoseRateModulation` | MU min⁻¹ deg⁻¹ | Dose rate variation divided by the arc length. |
| `MeanGantrySpeed` | deg s⁻¹ | Mean gantry speed. |
| `GantrySpeedModulation` | deg s⁻¹ deg⁻¹ | Gantry speed variation divided by the arc length. |
| `Q1MLCGap` | mm | First quartile of the distribution of opposing leaf pair openings. |
| `MedianMLCGap` | mm | Median of the distribution of opposing leaf pair openings. |
| `SAS10` | – | Small aperture score: fraction of opposing leaf pair openings smaller than 10 mm (0–1). Higher values mean the beam area is mostly made of gaps < 10 mm, which increases dosimetric uncertainty at the leaf tips. |
| `MeanTGI` | – | Mean tongue-and-groove index: ratio of the average distance between adjacent leaf tips to the mean MLC gap (0–1). Higher values mean smaller, irregularly shaped apertures and a larger tongue-and-groove effect. |
| `MCS` | – | Modulation complexity score: product of the variability in leaf positions and the irregularity of the aperture shape, MU-weighted (0–1). It is 1 for a fixed rectangular aperture and decreases with irregular apertures or leaf movement between control points. |
| `MITotal` | – | Total modulation index: global index combining MLC movement, gantry acceleration and dose-rate variation (≥ 0). Higher values mean more modulation. |
| `BI` | – | Beam irregularity: non-circularity of the MLC aperture, MU-weighted (≥ 1). Higher values mean the aperture is further from a circle and narrower. |
| `BM` | – | Beam modulation: extent of modulation in smaller apertures compared with the total beam area, MU-weighted (0–1). Close to 1 for a beam made of many small disconnected apertures. |
| `EdgeMetric` | mm⁻¹ | Average ratio between MLC side length ("edges") and aperture area, MU-weighted (≥ 0). Higher values mean a larger perimeter-to-area ratio: smaller, irregularly shaped apertures. |
| `LT/AL` | mm deg⁻¹ | Average in-field leaf travel divided by the arc length (≥ 0). Higher values mean more leaf travel between control points and more delivery uncertainty. |

### `MPC` (daily Machine Performance Check)

MPC is an automated daily linac check. Each run measures beam constancy and the geometric accuracy of
the collimator, gantry, couch and imaging isocentre. Column names follow `Group/Subgroup/Test [unit]`.
Values are deviations from the machine baseline. An empty cell means that test was not part of that run.

| Column(s) | Description |
|---|---|
| `Date` | Date and time of the run (text, `M/D/YYYY h:mm:ss AM/PM`). |
| `MachineName` | Linac (`LINAC_EDGE`, `LINAC_TB`). |
| `BeamGroup/BeamCenterShift [mm]` | Shift of the centre of an 18 × 18 cm² jaw-collimated field relative to the baseline. A summary of the precision of beam steering, collimation and the MV imaging system. |
| `BeamGroup/BeamOutputChange [%]` | Average change in detector response in the central area (12 × 12 cm²) of the portal imager. |
| `BeamGroup/BeamUniformityChange [%]` | Difference between the imager pixels with the lowest and highest ratio to the baseline in the central area (12 × 12 cm²). Reflects changes in the target and filter system and in beam steering. |
| `CollimationGroup/CollimationRotationOffset [°]` | Maximum deviation between nominal and actual collimator angle, from the edges of MLC comb patterns acquired at five collimator angles. |
| `CollimationGroup/JawsGroup/JawX1…Y2 [mm]` | Position error of each jaw. |
| `CollimationGroup/JawsParallelismGroup/…` | Jaw parallelism (°). |
| `CollimationGroup/MLCGroup/MLCLeavesA (or B)/MLCLeafN [mm]` | Position error of each MLC leaf (bank A/B, leaf N; 120 columns). |
| `CollimationGroup/MLCGroup/MLCMaxOffsetA`/`B`, `MLCMeanOffsetA`/`B` [mm] | Maximum and mean offset of the leaves of bank A and B, measured with a wave pattern of alternating leaves as the distance of the leaf tip from the MLC centre line. |
| `CollimationGroup/MLCGroup/MLCMeanSideOffset [mm]` | Mean lateral (side) offset of the leaves. |
| `CollimationGroup/MLCBacklashGroup/…/MLCBacklashLeafN [mm]` | Backlash (play) of each MLC leaf. |
| `CouchGroup/…`, `EnhancedCouchGroup/…` | Couch position errors (lateral, longitudinal, vertical in mm; pitch, roll, rotation in °). "Enhanced" tests use a different test procedure. |
| `EnhancedCouchGroup/CouchRtnLarge [°]` | Positioning accuracy of the couch angle for six positions between −90° and +90°, with pitch and roll of ±3°. |
| `EnhancedCouchGroup/RotationInducedCouchShiftFullRange [mm]` | Offset of the couch centre of rotation from the treatment isocentre, measured by rotating the couch to six positions between −90° and +90°, with pitch and roll of ±3°. |
| `GantryGroup/GantryAbsolute`, `GantryRelative [°]` | Gantry angle errors. |
| `IsoCenterGroup/IsoCenterSize [mm]` | Size of the radiation isocentre. |
| `IsoCenterGroup/IsoCenterMVOffset`, `IsoCenterKVOffset [mm]` | Offset of the MV and kV imager centres from the radiation isocentre. |

---

## Suggested project steps

1. **Explore** each raw table: what is a row, which columns are constant, which are missing, which are keys?
2. **Merge** the tables into one row per arc with its GPR, aPCMs and the MPC of the delivery day.
3. **Clean**: pick the right gamma criterion, deal with repeated measurements, harmonise units and keys,
   handle missing MPC days.
4. **Analyse**: GPR distribution, correlations between aPCMs (many are redundant), MPC trends over time.
5. **Model**: start from a simple baseline. **Split by patient**, not by arc (arcs of the same patient are
   correlated). Compare aPCM-only and aPCM + MPC models.
6. **Interpret**: which features matter? Is the model useful in the clinic?

---

## Repository layout

```
README.md                         this file
LICENSE.md                        PolyForm Noncommercial License 1.0.0
requirements.txt                  Python packages for local use
notebooks/gpr_prediction.ipynb    Colab notebook skeleton for students
tools/pseudonymise.py             instructor only: builds the pseudonymised data
tools/encrypt_data.py             instructor only: encrypts data files with a passkey
```

The data are **not** stored in this repository. They are shared as an encrypted archive on Google Drive.

---

## License

The code and documentation in this repository are licensed under the
[PolyForm Noncommercial License 1.0.0](LICENSE.md). You may use, change and share them for
noncommercial purposes only, such as teaching, academic research and personal study. Commercial use
is not allowed.

The license does not cover the data, which may be used only as described in [Data use rules](#data-use-rules).

Required Notice: Copyright (c) 2026 Nicola Lambri
