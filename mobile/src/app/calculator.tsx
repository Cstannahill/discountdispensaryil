import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Chip, Row, Section } from '@/components/ui';
import { calculateOtd, DEFAULT_LOCAL_PCT, inferExcisePct, LOCAL_PRESETS, MEDICAL_PCT, RATES_VERIFIED, STATE_SALES_PCT } from '@/lib/calculator';
import { money } from '@/lib/format';
import { C, MONO, WEB_TOP } from '@/lib/theme';
import { useAppState } from '@/state/store';

const EXCISE = [{ pct: 10, label: '≤35% THC · 10%' }, { pct: 20, label: 'Infused edible · 20%' }, { pct: 25, label: '>35% THC · 25%' }] as const;
const DISCOUNTS = [0, 10, 15, 20, 25, 30] as const;
const digits = (v: string) => v.replace(/[^0-9.]/g, '').replace(/(\..*)\./g, '$1').slice(0, 8);

function Field({ label, value, onChange, suffix }: { label: string; value: string; onChange: (v: string) => void; suffix: string }) {
  return (
    <View style={{ flex: 1, gap: 6 }}>
      <Text style={s.label}>{label}</Text>
      <View style={s.inputWrap}>
        <TextInput value={value} onChangeText={(v) => onChange(digits(v))} keyboardType="decimal-pad" inputMode="decimal" placeholder="0" placeholderTextColor={C.textFaint} accessibilityLabel={label} style={s.input} />
        <Text style={s.suffix}>{suffix}</Text>
      </View>
    </View>
  );
}

export default function CalculatorScreen() {
  const prefill = useAppState((st) => st.calc);
  const defaultLicense = useAppState((st) => st.filters.license);
  const [price, setPrice] = useState('');
  const [weight, setWeight] = useState('3.5');
  const [discount, setDiscount] = useState('0');
  const [medical, setMedical] = useState(defaultLicense === 'medicinal');
  const [excise, setExcise] = useState(10);
  const [local, setLocal] = useState(DEFAULT_LOCAL_PCT);
  const [label, setLabel] = useState<string | null>(null);

  // "OTD" on a deal card lands here with that deal's price, size and tax class filled in.
  useEffect(() => {
    if (!prefill) return;
    setPrice(prefill.price); setWeight(prefill.weight || '1'); setDiscount('0'); setLabel(prefill.label);
    setMedical(prefill.license === 'medicinal'); setExcise(inferExcisePct(prefill));
  }, [prefill]);

  const taxPct = medical ? MEDICAL_PCT : excise + STATE_SALES_PCT + local;
  const r = calculateOtd({ price: Number(price), weight: Number(weight), discountPct: Number(discount || 0), taxPct });
  const ok = r.valid && price !== '';

  return (
    <SafeAreaView style={s.screen} edges={['top']}>
      <KeyboardAvoidingView behavior={process.env.EXPO_OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
          <Text style={s.title} accessibilityRole="header">Out-the-door price</Text>
          <Text style={s.meta}>{label ?? 'Menu prices are before tax. Enter a price to see what you pay at the register.'}</Text>

          <View style={s.result} accessibilityLiveRegion="polite">
            <Text style={s.label}>You pay</Text>
            <Text style={s.big}>{ok ? money(r.outTheDoorTotal) : '—'}</Text>
            <Text style={s.meta}>{ok ? `${money(r.outTheDoorPerGram)}/g out the door · ${money(r.preTaxPerGram)}/g before tax · ${taxPct.toFixed(2)}% tax` : 'Enter a price and weight'}</Text>
          </View>

          <View style={{ flexDirection: 'row', gap: 10 }}>
            <Field label="Menu price" value={price} onChange={setPrice} suffix="$" />
            <Field label="Weight" value={weight} onChange={setWeight} suffix="g" />
            <Field label="Discount" value={discount} onChange={setDiscount} suffix="%" />
          </View>
          <Section title="Store discount">
            <Row>{DISCOUNTS.map((d) => <Chip key={d} label={d ? `${d}%` : 'None'} active={Number(discount || 0) === d} onPress={() => setDiscount(String(d))} />)}</Row>
          </Section>
          <Section title="License">
            <Row>
              <Chip label="Recreational" active={!medical} onPress={() => setMedical(false)} />
              <Chip label={`Medical · ${MEDICAL_PCT}%`} active={medical} onPress={() => setMedical(true)} />
            </Row>
          </Section>
          {!medical && (
            <>
              <Section title="Product excise tax">
                <Row>{EXCISE.map((e) => <Chip key={e.pct} label={e.label} active={excise === e.pct} onPress={() => setExcise(e.pct)} />)}</Row>
              </Section>
              <Section title="Local taxes">
                <Row>{LOCAL_PRESETS.map((p) => <Chip key={p.id} label={p.label} active={local === p.pct} onPress={() => setLocal(p.pct)} />)}</Row>
              </Section>
            </>
          )}
          <Text style={s.meta}>An estimate. Illinois rates last checked {RATES_VERIFIED}: {STATE_SALES_PCT}% state sales tax plus excise and local cannabis taxes, which vary by town and county.</Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg, paddingTop: WEB_TOP },
  content: { padding: 12, paddingBottom: 40, gap: 16, width: '100%', maxWidth: 720, alignSelf: 'center' },
  title: { color: C.text, fontSize: 24, fontWeight: '800' },
  meta: { color: C.textMuted, fontSize: 12, lineHeight: 17 },
  label: { color: C.textMuted, fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 },
  result: { backgroundColor: C.card, borderColor: C.accentBorder, borderWidth: 1, borderRadius: 18, padding: 16, gap: 4 },
  big: { color: C.accent, fontSize: 40, fontWeight: '800', fontFamily: MONO, fontVariant: ['tabular-nums'] },
  inputWrap: { flexDirection: 'row', alignItems: 'center', minHeight: 48, borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, paddingHorizontal: 12 },
  input: { flex: 1, color: C.text, fontSize: 18, fontFamily: MONO, paddingVertical: 8, minWidth: 0 },
  suffix: { color: C.textMuted, fontSize: 14, fontWeight: '700' },
});
