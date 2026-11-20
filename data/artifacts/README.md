# Wildlife road-safety knowledge base: curated research starter
Checked: 2026-11-20. Coverage: all six New England states and the province of New Brunswick, not all of Canada.

## Deliverables
23 source records and 28 tagged passage records, in CSV and JSONL. These are selected source excerpts and a discovery registry, NOT a complete PDF extraction or a downloaded crash-event dataset. No collision microdata or original PDF binaries are included. Text whitespace and bullet layout are normalized; excerpts are not always complete source paragraphs.

## Provenance and page metadata
Every excerpt has source URL, jurisdiction, section path, extraction basis and citation identifier. Null PDF page indices mean unverified, not zero. The Maine manual is Rev 11/23. Its table of contents verifies Wildlife Safety begins at printed 11-7; the returned full-document text was truncated. Manual excerpts come from search-extracted text, so subsection exact page indices remain unverified. The 11-7 label on the first manual record denotes the section start only. Do not promote it to exact passage pagination. HTML passages use section metadata, not artificial page numbers.

## Recommended ingestion completion
1. Download official PDF originals in an internet-enabled ingestion environment; record retrieval time, SHA-256, content type, publisher revision and license.
2. Extract each PDF page with pypdf or pdfplumber. Store one-based physical page index independently of printed labels; OCR only pages with missing text. Keep page boundaries and table bounding boxes; manually check folded brochures and charts.
3. Retrieve New Brunswick handbook Part 5 from its official index and resolve wildlife subsection pages. Extract Maine manual Wildlife Safety in full and verify every excerpt against page text.
4. Request or export event records separately from Maine crash query, MassDOT IMPACT, CTCDR and ROaDS. Vermont bulk database instructions target partnering organizations; do not assume public bulk permission. Ask NH, RI and NB custodians for event-level data where no verified download was found.
5. Record a license per source before redistribution. MaineDOT Wildlife Safety explicitly says All rights reserved. Government hosting is not equivalent to public-domain status.

## Proposed tags
Species tags deliberately retain deer rather than asserting a taxon absent from a passage. Add scientific names only after taxonomic validation. Never infer bear guidance merely because a source introduction mentions bears. Extend to turtles, amphibians, birds and other mammals as actual passages are ingested.
Scenario vocabulary: seasonal_risk, dawn_dusk, night_visibility, warning_signs, speed, roadside_scanning, rain_fog, habitat, headlights, multiple_animals, stopping_distance, animal_in_road, standoff, stay_in_vehicle, imminent_collision, road_salt, roadside_attraction, roadkill_reporting, injured_animal, species_identification, wildlife_fencing, collision_reporting.

## Safety and conflict controls
Maine says do not try to drive around a moose; NB discusses space when driving around one. Maine crash instructions include steer straight, release brakes before impact and duck; NB allows considering a safe swerve only if stopping is impossible. Preserve these as attributed jurisdiction-specific source language, NOT validated universal advice. safety_review_required flags emergency maneuvers and a cross-jurisdiction conflict. Prevent a retrieval system from synthesizing a new maneuver from incompatible excerpts; seek current road-safety authority review before user-facing emergency guidance.
NH evergreen page says April–November activity; its 2026 announcement emphasizes May–October high-risk months. Keep source date and exact scope rather than forcing one universal range.
Deduplicate Maine handbook, brochure and HTML by normalized text hash or similarity while preserving separate provenance. They are not independent corroboration.

## Collision table design (not populated)
event_id, source_id, jurisdiction, event_datetime_local, timezone, latitude, longitude, coordinate_precision_m, road_id, species_raw, species_normalized, observation_type, police_reported, injury_severity, reporting_threshold, survey_effort, source_record_id, data_dictionary_version, data_license.
Observation_type must distinguish police crash, carcass observation, live sighting, modeled crossing and published aggregate. Never pool them as interchangeable events. Preserve unknown species. Do not sum unmatched cross-source records without temporal-spatial deduplication. Survey effort and reporting thresholds differ, so raw counts do not provide comparable state risk or collision probability. Sensitive species coordinates may need suppression.

## Coverage limitations
All seven jurisdictions have source leads and guidance excerpts. Verified raw microdata acquisition is incomplete everywhere. RI and NH have guidance but no verified raw event export; NB has province-wide official guidance and historical map/chart resources but no verified province-wide event microdata. ROaDS describes regional coverage but that does not establish complete coverage of every state or province. Registry discovery status is not a claim of successful export. NB chart/map 2019 publisher dates must not be replaced by 2026 migration/search dates. CSV/JSONL excerpts contain source material and require rights review before external publication.
