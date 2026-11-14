import { useEffect, useMemo, useRef } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import MapView, { Marker } from 'react-native-maps';

import { money } from '@/lib/format';
import { regionFor } from '@/lib/geo';
import { C, MONO } from '@/lib/theme';
import type { MapStore } from '@/lib/types';

export interface StoreMapProps {
  stores: readonly MapStore[];
  center: { lat: number; lon: number };
  radius: number;
  unit: string;
  selectedId: string | null;
  hidden: readonly string[];
  showUser: boolean;
  /** The store with the lowest unit price on the map, highlighted. */
  bestId: string | null;
  onSelect: (id: string | null) => void;
}

/** The system map (Apple Maps on iPhone, Google Maps on Android) with one price pin per dispensary. */
export function StoreMap({ stores, center, radius, unit, selectedId, hidden, showUser, bestId, onSelect }: StoreMapProps) {
  const map = useRef<MapView>(null);
  const region = useMemo(() => regionFor(center, radius, stores), [center, radius, stores]);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; } // the first region is set by initialRegion
    map.current?.animateToRegion(region, 400);
  }, [region]);

  return (
    <MapView
      ref={map}
      style={StyleSheet.absoluteFill}
      initialRegion={region}
      userInterfaceStyle="dark"
      showsUserLocation={showUser}
      showsMyLocationButton={false}
      toolbarEnabled={false}
      rotateEnabled={false}
      pitchEnabled={false}
      onPress={() => onSelect(null)}>
      {stores.map((s) => {
        const off = hidden.includes(s.id), on = s.id === selectedId, top = s.id === bestId;
        const label = s.best ? `${money(s.best.unit_price)}/${unit}` : 'No deals';
        return (
          <Marker
            key={`${s.id}:${label}:${on}:${off}:${top}`}
            coordinate={{ latitude: s.latitude, longitude: s.longitude }}
            onPress={(e) => { e.stopPropagation(); onSelect(s.id); }}
            tracksViewChanges={false}
            zIndex={on ? 3 : top ? 2 : s.best ? 1 : 0}
            accessibilityLabel={`${s.name}, ${s.best ? `best ${label}` : 'no deals in this category'}`}>
            <View style={[st.pin, !s.best && st.pinEmpty, top && st.pinTop, on && st.pinOn, off && { opacity: 0.45 }]}>
              <Text style={[st.pinText, !s.best && { color: C.textMuted, fontFamily: undefined }, (top || on) && { color: C.bg }]}>{label}</Text>
            </View>
          </Marker>
        );
      })}
    </MapView>
  );
}

const st = StyleSheet.create({
  pin: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 12, borderWidth: 1.5, borderColor: C.accentStrong, backgroundColor: C.card },
  pinEmpty: { borderColor: C.border },
  pinTop: { backgroundColor: C.accent, borderColor: '#ffffff' },
  pinOn: { backgroundColor: '#fbbf24', borderColor: '#ffffff' },
  pinText: { color: C.accent, fontSize: 12, fontWeight: '800', fontFamily: MONO },
});
