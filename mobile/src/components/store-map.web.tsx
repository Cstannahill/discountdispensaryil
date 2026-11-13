import { Pressable, ScrollView, StyleSheet, Text } from 'react-native';

import { money } from '@/lib/format';
import { C, MONO } from '@/lib/theme';

import type { StoreMapProps } from './store-map';

/**
 * Browser stand-in for the native map, which only exists on phones: the same stores as a tappable list,
 * so the rest of the screen can be previewed and tested in a browser.
 */
export function StoreMap({ stores, unit, selectedId, hidden, bestId, onSelect }: StoreMapProps) {
  return (
    <ScrollView style={StyleSheet.absoluteFill} contentContainerStyle={st.list}>
      <Text style={st.note}>The map needs the phone app. Showing the same dispensaries as a list.</Text>
      {stores.map((s) => (
        <Pressable key={s.id} onPress={() => onSelect(s.id)} accessibilityRole="button" style={[st.row, s.id === selectedId && st.rowOn, hidden.includes(s.id) && { opacity: 0.45 }]}>
          <Text style={st.name} numberOfLines={1}>{s.id === bestId ? '★ ' : ''}{s.name}</Text>
          <Text style={[st.price, !s.best && { color: C.textMuted }]}>{s.best ? `${money(s.best.unit_price)}/${unit}` : 'No deals'}</Text>
        </Pressable>
      ))}
    </ScrollView>
  );
}

const st = StyleSheet.create({
  list: { padding: 12, paddingTop: 140, paddingBottom: 260, gap: 8 },
  note: { color: C.textMuted, fontSize: 12 },
  row: { minHeight: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, paddingHorizontal: 12, borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.card },
  rowOn: { borderColor: '#fbbf24' },
  name: { color: C.text, fontSize: 14, fontWeight: '600', flexShrink: 1 },
  price: { color: C.accent, fontSize: 13, fontWeight: '800', fontFamily: MONO },
});
