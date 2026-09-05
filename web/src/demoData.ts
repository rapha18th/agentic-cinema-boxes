import type { Evidence, ResearchBox, ResearchRun, Verdict } from "./types";

export const DEMO_PREMISE = "In 1958, a young Black mathematician is pulled into the political struggle to turn a fractured wartime rocket programme into NASA.";

export const DEMO_BOXES: ResearchBox[] = [
  { id: "obj01", name: "FOUNDING MANDATE", description: "The political bargain, public language, and institutional powers behind NASA's creation.", rationale: "The inciting decision needs a credible political mechanism.", score: .91, evidence_count: 8, distinct_domains: 5, departments: ["script", "casting"] },
  { id: "obj02", name: "SEGREGATED COMPUTING", description: "Working conditions, titles, pay, and daily routines for Black women mathematicians in 1958.", rationale: "The protagonist's authority and constraints must be specific.", score: .88, evidence_count: 9, distinct_domains: 4, departments: ["script", "casting", "costume", "art_direction"] },
  { id: "obj03", name: "LANGLEY INTERIORS", description: "The physical texture of offices, wind tunnels, calculation rooms, and machine shops.", rationale: "Production design needs buildable spaces rather than generic laboratories.", score: .84, evidence_count: 7, distinct_domains: 4, departments: ["art_direction", "cinematography", "locations"] },
  { id: "obj04", name: "SOUND OF CALCULATION", description: "Mechanical calculators, teletypes, test cells, and the acoustic rhythm of technical work.", rationale: "Sound can make invisible intellectual labour cinematic.", score: .72, evidence_count: 6, distinct_domains: 3, departments: ["sound", "cinematography"] },
  { id: "obj05", name: "ARMY TO CIVILIAN", description: "How military rocket personnel, records, and loyalties moved into a civilian agency.", rationale: "The institutional conflict needs people with incompatible histories.", score: .64, evidence_count: 5, distinct_domains: 3, departments: ["script", "casting"], emergent: true },
  { id: "obj06", name: "HAMPTON STREETS", description: "Transport, housing, shops, food, dress, and racial geography around Langley.", rationale: "The film needs a lived world beyond the research centre.", score: .58, evidence_count: 4, distinct_domains: 2, departments: ["costume", "art_direction", "locations"] },
];

const ev = (id: string, objective_id: string, title: string, source_domain: string, text: string, round: number, source_tier = "documentary") : Evidence => ({
  id, objective_id, title, source_domain, text, round, modality: "text",
  url: `https://${source_domain}/`, publish_date: round ? "1958" : "2024",
  source_tier, quality_score: source_tier === "primary" ? .96 : .82,
});

export const DEMO_EVIDENCE: Evidence[] = [
  ev("e01", "obj01", "National Aeronautics and Space Act of 1958", "govinfo.gov", "The Act created a civilian agency and charged it with the expansion of human knowledge of phenomena in the atmosphere and space.", 0, "primary"),
  ev("e02", "obj01", "Eisenhower statement on signing the Space Act", "presidency.ucsb.edu", "The administration publicly framed the new agency around peaceful purposes while national security activity remained separated.", 0, "primary"),
  ev("e03", "obj02", "Hidden Figures oral history collection", "nasa.gov", "Former Langley computers describe segregated offices, changing job titles, hand calculation, and the informal routes through which difficult assignments were distributed.", 0, "primary"),
  ev("e04", "obj02", "West Area Computers archival guide", "archives.gov", "Personnel records distinguish the formal classification system from the technical responsibility women already carried in practice.", 0, "primary"),
  ev("e05", "obj03", "Langley building plans and photographs", "loc.gov", "Calculation rooms used long shared tables, task lighting, chalkboards, mechanical calculators, and visible paper circulation between desks.", 0, "primary"),
  ev("e06", "obj03", "Full-scale tunnel technical memorandum", "ntrs.nasa.gov", "The tunnel complex joined offices and test infrastructure through observation rooms, instrument spaces, and heavy industrial circulation.", 0, "primary"),
  ev("e07", "obj04", "Friden calculator operating manual", "si.edu", "The calculator's carriage, motor, and repeated-cycle mechanism produce a distinct sequence of clacks, whirring, and return impacts.", 1, "primary"),
  ev("e08", "obj04", "Langley test-cell recordings", "archive.org", "Archival recordings place speech under ventilation, relay chatter, warning bells, and low-frequency machinery.", 1, "primary"),
  ev("e09", "obj05", "NACA to NASA transition history", "history.nasa.gov", "The transfer was not a clean founding moment. Existing laboratories, staff, and procedures became the core of the new agency.", 1, "primary"),
  ev("e10", "obj05", "Army Ballistic Missile Agency chronology", "army.mil", "The Army programme remained institutionally separate through NASA's opening months, complicating a simple overnight transfer narrative.", 1, "primary"),
  ev("e11", "obj06", "Hampton city directory, 1958", "archive.org", "The directory fixes businesses, bus routes, churches, addresses, and professional listings in the streets surrounding Langley.", 1, "primary"),
  ev("e12", "obj06", "Virginia travel survey", "virginia.gov", "Regional road and bus records show that commuting access depended heavily on neighbourhood and shift time.", 1, "documentary"),
];

export const DEMO_RUNS: ResearchRun[] = [
  { run: 0, sources_examined: 24, sources_extracted: 10, evidence_indexed: 8, coverage_before: 0, coverage_after: .62, confidence_before: 0, confidence_after: .66, searches: [
    { objective: "SEGREGATED COMPUTING", queries: ["site:nasa.gov Langley West Area Computers oral history 1958"] },
    { objective: "LANGLEY INTERIORS", queries: ["site:ntrs.nasa.gov Langley laboratory plans 1958 calculation room"] },
  ], next_action: "investigate the transfer from military rocketry to the civilian agency" },
  { run: 1, sources_examined: 18, sources_extracted: 7, evidence_indexed: 4, coverage_before: .62, coverage_after: .76, confidence_before: .66, confidence_after: .81, new_boxes: ["ARMY TO CIVILIAN"], conflicts: ["NASA transition history vs Army chronology"], searches: [
    { objective: "ARMY TO CIVILIAN", queries: ["1958 Army Ballistic Missile Agency NASA transfer chronology primary source"] },
  ], next_action: "production brief ready; flag the transfer timeline for writer review" },
];

export const DEMO_VERDICTS: Verdict[] = [{
  id: "v01", relation: "contextualises", similarity: .79,
  explanation: "NASA inherited NACA laboratories immediately, but the Army rocket programme did not transfer wholesale at the same moment. The screenplay should treat these as separate institutional transitions.",
  a_cite: "NACA to NASA transition history · history.nasa.gov",
  b_cite: "Army Ballistic Missile Agency chronology · army.mil",
}];
