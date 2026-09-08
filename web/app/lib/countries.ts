// GENERATED from collector/sources/countries.py + world-atlas countries-110m.
// Do not hand-edit: numeric ids must match the topology the map draws, so they
// are derived from it rather than typed in.
//
// `numeric` is the ISO-3166 numeric id world-atlas keys shapes by; it is null for
// territories too small to appear in the 110m topology (city-states, atolls).
// Those still render in the country LIST, they just cannot be shaded on the map.

export interface CountryInfo {
  name: string;
  numeric: string | null;
}

export const COUNTRIES: Record<string, CountryInfo> = {
  AE: { name: "United Arab Emirates", numeric: "784" },
  AR: { name: "Argentina", numeric: "032" },
  AT: { name: "Austria", numeric: "040" },
  AU: { name: "Australia", numeric: "036" },
  BE: { name: "Belgium", numeric: "056" },
  BR: { name: "Brazil", numeric: "076" },
  BY: { name: "Belarus", numeric: "112" },
  CA: { name: "Canada", numeric: "124" },
  CD: { name: "DR Congo", numeric: "180" },
  CH: { name: "Switzerland", numeric: "756" },
  CL: { name: "Chile", numeric: "152" },
  CN: { name: "China", numeric: "156" },
  CO: { name: "Colombia", numeric: "170" },
  CZ: { name: "Czechia", numeric: "203" },
  DE: { name: "Germany", numeric: "276" },
  DK: { name: "Denmark", numeric: "208" },
  EG: { name: "Egypt", numeric: "818" },
  ES: { name: "Spain", numeric: "724" },
  FI: { name: "Finland", numeric: "246" },
  FR: { name: "France", numeric: "250" },
  GB: { name: "United Kingdom", numeric: "826" },
  GH: { name: "Ghana", numeric: "288" },
  GR: { name: "Greece", numeric: "300" },
  HK: { name: "Hong Kong", numeric: null },
  ID: { name: "Indonesia", numeric: "360" },
  IE: { name: "Ireland", numeric: "372" },
  IL: { name: "Israel", numeric: "376" },
  IN: { name: "India", numeric: "356" },
  IS: { name: "Iceland", numeric: "352" },
  IT: { name: "Italy", numeric: "380" },
  JP: { name: "Japan", numeric: "392" },
  KR: { name: "South Korea", numeric: "410" },
  KW: { name: "Kuwait", numeric: "414" },
  KZ: { name: "Kazakhstan", numeric: "398" },
  MA: { name: "Morocco", numeric: "504" },
  MC: { name: "Monaco", numeric: null },
  MH: { name: "Marshall Islands", numeric: null },
  MN: { name: "Mongolia", numeric: "496" },
  MX: { name: "Mexico", numeric: "484" },
  MY: { name: "Malaysia", numeric: "458" },
  NA: { name: "Namibia", numeric: "516" },
  NG: { name: "Nigeria", numeric: "566" },
  NL: { name: "Netherlands", numeric: "528" },
  NO: { name: "Norway", numeric: "578" },
  NZ: { name: "New Zealand", numeric: "554" },
  PA: { name: "Panama", numeric: "591" },
  PE: { name: "Peru", numeric: "604" },
  PH: { name: "Philippines", numeric: "608" },
  PL: { name: "Poland", numeric: "616" },
  PT: { name: "Portugal", numeric: "620" },
  PY: { name: "Paraguay", numeric: "600" },
  QA: { name: "Qatar", numeric: "634" },
  RU: { name: "Russia", numeric: "643" },
  SA: { name: "Saudi Arabia", numeric: "682" },
  SE: { name: "Sweden", numeric: "752" },
  SG: { name: "Singapore", numeric: null },
  TH: { name: "Thailand", numeric: "764" },
  TR: { name: "Turkey", numeric: "792" },
  TW: { name: "Taiwan", numeric: "158" },
  UA: { name: "Ukraine", numeric: "804" },
  US: { name: "United States", numeric: "840" },
  UZ: { name: "Uzbekistan", numeric: "860" },
  VN: { name: "Vietnam", numeric: "704" },
  ZA: { name: "South Africa", numeric: "710" },
};

/** ISO numeric -> ISO2, for looking a map shape back up to our data. */
export const NUMERIC_TO_ISO2: Record<string, string> = Object.fromEntries(
  Object.entries(COUNTRIES)
    .filter(([, v]) => v.numeric)
    .map(([iso2, v]) => [v.numeric as string, iso2]),
);

export function countryName(iso2: string): string {
  return COUNTRIES[iso2]?.name ?? iso2;
}
