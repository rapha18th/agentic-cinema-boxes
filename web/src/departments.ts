/** Fixed vocabulary, mirrors src/boxes/ontology.py DEPARTMENTS. A box can
 *  serve more than one department. */
export const DEPARTMENTS = [
  "script", "casting", "costume", "art_direction", "sound", "cinematography", "locations",
] as const;

export const DEPT_LABEL: Record<string, string> = {
  script: "Script",
  casting: "Casting",
  costume: "Costume",
  art_direction: "Art direction",
  sound: "Sound",
  cinematography: "Cinematography",
  locations: "Locations",
};
