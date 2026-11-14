import { useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiError, geocode } from '@/lib/api';
import { success, warning } from '@/lib/haptics';
import { currentFix } from '@/lib/location';
import { C } from '@/lib/theme';
import { QUICK_HUBS, RADII } from '@/lib/types';
import { setFilters, setOrigin, useAppState } from '@/state/store';

import { Button, Chip, Row, Section, Sheet } from './ui';

export function LocationSheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const origin = useAppState((s) => s.origin);
  const radius = useAppState((s) => s.filters.radius);
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const useGps = async () => {
    setBusy('gps'); setMsg(null);
    const fix = await currentFix(true);
    setBusy(null);
    if (fix.ok) { setOrigin(fix.origin); success(); onClose(); }
    else { warning(); setMsg(fix.reason === 'denied' ? 'Location permission is off. Allow it in Settings, or enter a ZIP or city below.' : 'Could not read your location. Enter a ZIP or city below.'); }
  };

  const lookup = async (text: string, label?: string) => {
    const t = text.trim();
    if (t.length < 3) { setMsg('Enter a ZIP or City, ST.'); return; }
    setBusy(label ?? 'search'); setMsg(null);
    try {
      const r = await geocode(t);
      setOrigin({ lat: r.latitude, lon: r.longitude, place: label ?? r.label, src: 'manual', at: Date.now() });
      setQ(''); success(); onClose();
    } catch (e) {
      warning();
      setMsg(e instanceof ApiError && e.status === 0 ? 'No connection. Try again when you are back online.' : (e as Error).message);
    } finally { setBusy(null); }
  };

  return (
    <Sheet visible={visible} title="Search location" onClose={onClose}>
      {origin && <Text style={s.current}>Searching near <Text style={{ color: C.accent, fontWeight: '700' }}>{origin.place}</Text>{origin.src === 'gps' ? ' (your location, re-checked each time you open the app)' : ''}</Text>}
      <Button label={busy === 'gps' ? 'Finding you…' : '📍 Use my current location'} onPress={useGps} disabled={!!busy} />
      <Section title="ZIP or city">
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TextInput
            value={q}
            onChangeText={setQ}
            onSubmitEditing={() => lookup(q)}
            placeholder="60601 or Peoria, IL"
            placeholderTextColor={C.textFaint}
            returnKeyType="search"
            autoCorrect={false}
            accessibilityLabel="ZIP or city"
            style={s.input}
          />
          <Button label="Search" onPress={() => lookup(q)} disabled={!!busy} />
        </View>
        {busy && busy !== 'gps' && <ActivityIndicator color={C.accent} />}
        {!!msg && <Text style={s.msg} accessibilityRole="alert">{msg}</Text>}
      </Section>
      <Section title="Popular areas">
        <Row>{QUICK_HUBS.map(([name, zip]) => <Chip key={zip} label={name} active={origin?.src === 'manual' && origin.place === name} onPress={() => lookup(zip, name)} />)}</Row>
      </Section>
      <Section title="Distance">
        <Row>{RADII.map((r) => <Chip key={r} label={`${r} mi`} active={radius === r} onPress={() => setFilters({ radius: r })} />)}</Row>
      </Section>
    </Sheet>
  );
}

const s = StyleSheet.create({
  current: { color: C.textSoft, fontSize: 14, lineHeight: 20 },
  input: { flex: 1, minHeight: 44, borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.cardAlt, color: C.text, paddingHorizontal: 12, fontSize: 16 },
  msg: { color: C.warn, backgroundColor: C.warnBg, borderColor: C.warnBorder, borderWidth: 1, borderRadius: 12, padding: 10, fontSize: 13, overflow: 'hidden' },
});
