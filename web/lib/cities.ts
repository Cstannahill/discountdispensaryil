// Illinois metro hubs that get their own indexable page. Mirrors QUICK_HUBS (same ZIPs) with fixed coordinates, so no geocoding at render time.
export interface City {
  slug: string;
  name: string;
  zip: string;
  latitude: number;
  longitude: number;
  radius_miles: number;
  blurb: string;
}

export const CITIES: readonly City[] = [
  { slug: 'chicago', name: 'Chicago', zip: '60601', latitude: 41.8858, longitude: -87.6181, radius_miles: 15, blurb: 'Dozens of recreational dispensaries compete inside the city, so the lowest price per gram usually sits at a different shop for each category.' },
  { slug: 'naperville', name: 'Naperville', zip: '60540', latitude: 41.7508, longitude: -88.1535, radius_miles: 20, blurb: 'Western suburban dispensaries around Naperville, Aurora and Lisle.' },
  { slug: 'joliet', name: 'Joliet', zip: '60431', latitude: 41.525, longitude: -88.0817, radius_miles: 25, blurb: 'Dispensaries across Will County, from Joliet to Plainfield and Romeoville.' },
  { slug: 'rockford', name: 'Rockford', zip: '61101', latitude: 42.2711, longitude: -89.094, radius_miles: 25, blurb: 'Northern Illinois dispensaries in and around Rockford and Loves Park.' },
  { slug: 'quad-cities', name: 'Quad Cities', zip: '61265', latitude: 41.4985, longitude: -90.5187, radius_miles: 30, blurb: 'Illinois-side dispensaries near Moline, Rock Island and East Moline.' },
  { slug: 'peoria', name: 'Peoria', zip: '61602', latitude: 40.6936, longitude: -89.589, radius_miles: 25, blurb: 'Central Illinois dispensaries around Peoria, East Peoria and Pekin.' },
  { slug: 'normal', name: 'Bloomington-Normal', zip: '61761', latitude: 40.5142, longitude: -88.9906, radius_miles: 25, blurb: 'Dispensaries in Bloomington, Normal and the surrounding McLean County area.' },
  { slug: 'champaign', name: 'Champaign-Urbana', zip: '61820', latitude: 40.1164, longitude: -88.2434, radius_miles: 25, blurb: 'Dispensaries in Champaign, Urbana and nearby towns.' },
  { slug: 'springfield', name: 'Springfield', zip: '62701', latitude: 39.7817, longitude: -89.6501, radius_miles: 30, blurb: 'State capital dispensaries around Springfield and Sherman.' },
  { slug: 'streator', name: 'Streator', zip: '61358', latitude: 41.1217, longitude: -88.8361, radius_miles: 30, blurb: 'Dispensaries in the Illinois Valley around Streator, Ottawa and LaSalle.' },
  { slug: 'metro-east', name: 'Metro East (St. Louis area)', zip: '62234', latitude: 38.6703, longitude: -89.9846, radius_miles: 25, blurb: 'Illinois dispensaries just across the river from St. Louis, including Collinsville and Fairview Heights.' },
  { slug: 'carbondale', name: 'Carbondale', zip: '62901', latitude: 37.7273, longitude: -89.2167, radius_miles: 40, blurb: 'Southern Illinois dispensaries around Carbondale and Marion.' },
];

export const cityBySlug = (slug: string) => CITIES.find((c) => c.slug === slug);
