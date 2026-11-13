import { StyleSheet, Switch, Text, View } from 'react-native';

import { C } from '@/lib/theme';
import { GRADES, SORT_LABEL, SORT_OPTIONS, STRAINS, sizesFor } from '@/lib/types';
import { resetFilters, setFilters, useAppState } from '@/state/store';

import { Button, Chip, Row, Section, Sheet } from './ui';

const GRADE_LABEL = { whole: 'Whole flower', smalls: 'Smalls', shake: 'Shake', infused: 'Infused', all: 'All grades' } as const;

function Toggle({ label, hint, value, onChange }: { label: string; hint: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <View style={s.toggle}>
      <View style={{ flex: 1 }}>
        <Text style={s.toggleLabel}>{label}</Text>
        <Text style={s.toggleHint}>{hint}</Text>
      </View>
      <Switch value={value} onValueChange={onChange} trackColor={{ true: C.accentStrong, false: C.border }} accessibilityLabel={label} />
    </View>
  );
}

export function FilterSheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const f = useAppState((s) => s.filters);
  return (
    <Sheet visible={visible} title="Sort and filter" onClose={onClose}>
      <Section title="Sort by">
        <Row>{SORT_OPTIONS.map((o) => <Chip key={o} label={SORT_LABEL[o]} active={f.sort === o} onPress={() => setFilters({ sort: o })} />)}</Row>
      </Section>
      {f.category === 'flower' && (
        <Section title="Flower grade">
          <Row>{GRADES.map((g) => <Chip key={g} label={GRADE_LABEL[g]} active={f.grade === g} onPress={() => setFilters({ grade: g })} />)}</Row>
        </Section>
      )}
      <Section title="Strain">
        <Row>
          <Chip label="Any" active={!f.strain} onPress={() => setFilters({ strain: '' })} />
          {STRAINS.map((t) => <Chip key={t} label={t} active={f.strain === t} onPress={() => setFilters({ strain: t })} />)}
        </Row>
      </Section>
      {f.category !== 'edibles' && (
        <Section title="Size">
          <Row>{sizesFor(f.category).map((z) => <Chip key={z} label={z === 'any' ? 'Any' : `${z}g`} active={f.size === z} onPress={() => setFilters({ size: z })} />)}</Row>
        </Section>
      )}
      <Toggle label="Show older menus" hint="Also list menus older than 12 hours from stores that have a newer one." value={f.stale} onChange={(v) => setFilters({ stale: v })} />
      <Toggle label="Include unverified" hint="Add menus whose totals could not be fully confirmed, and unusually low prices." value={f.unverified} onChange={(v) => setFilters({ unverified: v })} />
      <Button kind="ghost" label="Reset filters" onPress={resetFilters} />
    </Sheet>
  );
}

const s = StyleSheet.create({
  toggle: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 44 },
  toggleLabel: { color: C.text, fontSize: 15, fontWeight: '600' },
  toggleHint: { color: C.textMuted, fontSize: 12, lineHeight: 16, marginTop: 2 },
});
