# GOES Historical Date Ranges Design

## Goal

Add GOES-16 and GOES-17 historical Full Disk support and prevent users from selecting dates outside each satellite's supported archive period.

## Confirmed Scope

- Satellites shown in the manual selector:
  - `GOES-16`
  - `GOES-17（历史）`
  - `GOES-18`
  - `GOES-19`
- Reuse the current GOES provider and renderer capabilities:
  - NOAA `ABI-L2-CMIPF`
  - Full Disk only
  - IR, WV, VIS
  - UTC ten-minute slots: `00`, `10`, `20`, `30`, `40`, `50`
- No automatic satellite switching.
- No RGB, regional domains, animation, or new product types in this change.

## Satellite Archive Windows

These are product-facing default windows for the first release. A request inside a window can still fail if the exact NOAA object is absent; the application must retain the existing clear missing-slot error.

| Satellite | Earliest selectable UTC date | Latest selectable UTC date | User-facing note |
|---|---:|---:|---|
| GOES-16 | 2017-12-18 | 2025-04-06 | GOES-East historical/standby boundary |
| GOES-17 | 2018-12-04 | 2023-01-10 | Historical satellite |
| GOES-18 | 2023-01-04 | no fixed end date | Current GOES-West archive |
| GOES-19 | 2025-04-07 | no fixed end date | Current GOES-East archive |

GOES-17 must display as `GOES-17（历史）` in the GUI, while provider/API identifiers remain the stable string `GOES-17`.

## User Experience

- When a satellite changes, the date control updates to the selected satellite's valid window.
- If the current date is outside the new window, it is clamped to the nearest valid date and the UI visibly reflects the changed date.
- The date control must prevent choosing dates outside the window, rather than allowing a request that is guaranteed to fail.
- The time control remains restricted to ten-minute UTC slots for all GOES satellites.
- A date inside the window but without a specific file shows the existing actionable missing-data message and does not substitute a neighboring scan.
- If the user attempts an out-of-window date through a non-GUI/API boundary, raise a clear `ValueError` before any S3 listing.

## Architecture

Extend `PROVIDER_CONFIGS` with display label, minimum date, and maximum date metadata. Keep platform identifiers separate from display labels. Add one pure validation helper for a requested UTC date and use it in both the public drawing entry and GUI state synchronization.

The data provider continues to derive the S3 bucket from the platform identifier. GOES-16 and GOES-17 use `noaa-goes16` and `noaa-goes17`; no new reader or renderer branch is needed.

## Acceptance Tests

Automated tests must cover:

- Four provider configurations and exact archive bounds.
- GOES-17 display label differs from its stable provider identifier.
- Dates at both boundaries are accepted.
- Dates immediately outside each finite window are rejected before `fs.ls` or any network access.
- GOES-18 and GOES-19 future/open-ended dates remain valid at the configuration layer.
- GUI switching clamps an out-of-window current date and preserves a valid ten-minute time slot.
- Existing GOES-18/19 and Himawari tests remain green.

## Data Sources

- NOAA Open Data Registry: `https://registry.opendata.aws/noaa-goes/`
- GOES-17 MCMIPF availability reference: `https://developers.google.com/earth-engine/datasets/catalog/NOAA_GOES_17_MCMIPF`
- GOES-R Beginner's Guide and operational transition table: `https://www.ospo.noaa.gov/resources/documents/PDFs/Beginners_Guide_to_GOES-R_Series_Data.pdf`
- GOES-19 MCMIPF availability reference: `https://developers.google.com/earth-engine/datasets/catalog/NOAA_GOES_19_MCMIPF`

## Deferred UI Work

UI visual polish and animation are explicitly deferred to a separate design and implementation cycle after historical date validation is accepted. That cycle must not change provider semantics, date boundaries, task invalidation, or error behavior.
