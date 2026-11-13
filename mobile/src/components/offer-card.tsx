import * as WebBrowser from 'expo-web-browser';
import { router } from 'expo-router';
import { memo, useState } from 'react';
import { Alert, Linking, Pressable, Share, StyleSheet, Text, View } from 'react-native';

import { calculateSavings } from '@/lib/calculator';
import { cardTitle, directionsUrl, freshnessLabel, isGrouped, massLabel, money, perUnit, relativeTime, safeUrl, shareText, strainBucket, unitLabel } from '@/lib/format';
import { bump, success, tap } from '@/lib/haptics';
import { C, MONO } from '@/lib/theme';
import type { Offer } from '@/lib/types';
import { openCalculatorWith, setStoreHidden, toggleSaved, useAppState } from '@/state/store';

import { Badge, Button, toast } from './ui';

const STRAIN_COLOR = { Indica: C.indica, Sativa: C.sativa, Hybrid: C.hybrid, Unspecified: C.textMuted } as const;

/** Opens a dispensary menu in the in-app browser so the user lands back on their results when they close it. */
export async function openMenu(url: string) {
  try { await WebBrowser.openBrowserAsync(url, { toolbarColor: C.bg, controlsColor: C.accent }); }
  catch { Linking.openURL(url).catch(() => toast('Could not open the menu')); }
}

export const openDirections = (store: string, place?: Parameters<typeof directionsUrl>[1]) => { Linking.openURL(directionsUrl(store, place)).catch(() => toast('Could not open maps')); };

export function shareOffer(o: Offer) {
  const url = safeUrl(o.source_url);
  Share.share({ title: `DiscountDispensaryIL: ${cardTitle(o)}`, message: url ? `${shareText(o)}\n${url}` : shareText(o) }).catch(() => {});
}

function confirmHide(o: Offer) {
  bump();
  Alert.alert(o.store_name, 'Hide this dispensary from your results? You can show it again on the Stores tab.', [
    { text: 'Cancel', style: 'cancel' },
    { text: 'Hide', style: 'destructive', onPress: () => toast(setStoreHidden(o.store_id, o.store_name, true) ? `${o.store_name} hidden` : 'You can hide up to 100 dispensaries') },
  ]);
}

function OfferCardImpl({ o, rank }: { o: Offer; rank?: number }) {
  const saved = useAppState((s) => s.saved.some((x) => x.id === o.id));
  const [open, setOpen] = useState(false);
  const grouped = isGrouped(o);
  const href = safeUrl(o.source_url);
  const savings = calculateSavings(o.regular_price, o.effective_price);
  const fresh = freshnessLabel(o);
  const unit = unitLabel(o.category);
  const title = cardTitle(o);
  const mass = massLabel(o);

  return (
    <View style={s.card} accessibilityLabel={`${title}, ${mass}, ${money(perUnit(o))} per ${unit}, ${money(o.effective_price)} at ${o.store_name}, ${o.distance_miles.toFixed(1)} miles`}>
      <View style={s.top}>
        <View style={{ flex: 1, gap: 4 }}>
          <View style={s.line}>
            {rank != null && rank <= 3 && <Badge color={C.accent} border={C.accentBorder} bg={C.accentBg}>#{rank}</Badge>}
            <Text style={s.brand} numberOfLines={1}>{o.brand || 'Brand not supplied'}</Text>
          </View>
          <Text style={s.name}>{title}</Text>
          <View style={s.badges}>
            {!grouped && !!o.strain_type && <Badge color={STRAIN_COLOR[strainBucket(o.strain_type)]}>{o.strain_type}</Badge>}
            {!!o.flower_grade && o.flower_grade !== 'whole' && <Badge color={C.warn} border={C.warnBorder} bg={C.warnBg}>{o.flower_grade}</Badge>}
            <Badge>{mass}</Badge>
            {!grouped && !!o.thc_pct && <Badge>THC {o.thc_pct}%</Badge>}
          </View>
        </View>
        <View style={s.price}>
          {savings.hasDiscount && <Text style={s.off}>{savings.savingsPct}% OFF</Text>}
          <Text style={s.unitPrice}>{money(perUnit(o))}<Text style={s.unit}>/{unit}</Text></Text>
          <Text style={s.total}>
            {savings.hasDiscount && <Text style={s.was}>{money(o.regular_price)} </Text>}
            {money(o.effective_price)}
          </Text>
        </View>
      </View>

      <View style={s.meta}>
        <Pressable
          style={({ pressed }) => [s.store, pressed && { opacity: 0.6 }]}
          onPress={() => openDirections(o.store_name)}
          onLongPress={() => confirmHide(o)}
          accessibilityRole="link"
          accessibilityLabel={`Directions to ${o.store_name}`}
          accessibilityHint="Long press to hide this dispensary">
          <Text style={s.storeName} numberOfLines={1}>📍 {o.store_name}</Text>
          <Badge color={C.accent} border={C.accentBorder}>{o.distance_miles.toFixed(1)} mi</Badge>
          <Text style={s.lic}>{o.license_type === 'medicinal' ? 'MED' : 'REC'}</Text>
        </Pressable>
        <Badge color={fresh.ok ? C.accent : C.warn} border={fresh.ok ? C.accentBorder : C.warnBorder}>{fresh.text}</Badge>
      </View>
      <Text style={s.updated}>Updated {relativeTime(o.last_seen_at)}{o.conditional ? ' · Conditional promotion' : ''}</Text>

      {grouped && (
        <View style={s.variants}>
          <Pressable onPress={() => { tap(); setOpen((v) => !v); }} accessibilityRole="button" accessibilityState={{ expanded: open }} style={s.variantsHead}>
            <Text style={s.variantsTitle}>🌿 {o.variants!.length} strains at this price</Text>
            <Text style={s.updated}>{open ? 'Hide' : 'Show'}</Text>
          </Pressable>
          {open && o.variants!.map((v) => {
            const u = safeUrl(v.source_url);
            return (
              <Pressable key={v.id} disabled={!u} onPress={() => u && openMenu(u)} style={s.variant} accessibilityRole={u ? 'link' : 'text'}>
                <Text style={[s.variantName, { color: STRAIN_COLOR[strainBucket(v.strain_type)] }]} numberOfLines={1}>{v.name}{u ? ' ↗' : ''}</Text>
                {!!v.thc_pct && <Text style={s.updated}>{v.thc_pct}% THC</Text>}
              </Pressable>
            );
          })}
        </View>
      )}

      <View style={s.actions}>
        {href
          ? <Button label="Menu ↗" a11y={`View ${title} on the dispensary menu`} onPress={() => openMenu(href)} style={{ flex: 1 }} />
          : <Text style={[s.updated, { flex: 1 }]}>Menu link unavailable</Text>}
        <Button
          kind="ghost"
          label={saved ? '★ Saved' : '☆ Save'}
          a11y={saved ? `Remove ${title} from saved deals` : `Save ${title}`}
          onPress={() => { const on = toggleSaved(o); if (on) success(); else tap(); toast(on ? 'Saved. We will flag price changes.' : 'Removed from saved deals'); }}
        />
        <Button kind="ghost" label="Share" a11y={`Share ${title}`} onPress={() => shareOffer(o)} />
        {o.category !== 'edibles' && (
          <Button
            kind="ghost"
            label="OTD"
            a11y={`Out the door price for ${title}`}
            onPress={() => {
              openCalculatorWith({ price: o.effective_price ?? '', weight: o.weight_grams ?? '', license: o.license_type, category: o.category, flower_grade: o.flower_grade, thc_pct: o.thc_pct ?? null, label: `${title} · ${o.store_name}` });
              router.navigate('/calculator');
            }}
          />
        )}
      </View>
    </View>
  );
}

export const OfferCard = memo(OfferCardImpl);

const s = StyleSheet.create({
  card: { backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 18, padding: 14, gap: 10 },
  top: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  line: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  brand: { color: C.accent, fontSize: 11, fontWeight: '800', letterSpacing: 0.8, textTransform: 'uppercase', flexShrink: 1 },
  name: { color: C.text, fontSize: 15, fontWeight: '700', lineHeight: 20 },
  badges: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 2 },
  price: { alignItems: 'flex-end', backgroundColor: C.cardAlt, borderColor: C.borderSoft, borderWidth: 1, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 8 },
  off: { color: C.accent, fontSize: 10, fontWeight: '800', marginBottom: 3 },
  unitPrice: { color: C.accent, fontSize: 21, fontWeight: '800', fontFamily: MONO, fontVariant: ['tabular-nums'] },
  unit: { color: C.textMuted, fontSize: 11, fontWeight: '400' },
  total: { color: C.textSoft, fontSize: 12, fontWeight: '700', fontFamily: MONO, marginTop: 3 },
  was: { color: C.textFaint, fontWeight: '400', textDecorationLine: 'line-through' },
  meta: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, borderTopWidth: 1, borderTopColor: C.borderSoft, paddingTop: 10 },
  store: { flexDirection: 'row', alignItems: 'center', gap: 6, flexShrink: 1, minHeight: 28 },
  storeName: { color: C.textSoft, fontSize: 13, fontWeight: '600', flexShrink: 1 },
  lic: { color: C.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 0.6 },
  updated: { color: C.textMuted, fontSize: 11 },
  variants: { backgroundColor: C.cardAlt, borderColor: C.borderSoft, borderWidth: 1, borderRadius: 12, paddingHorizontal: 12 },
  variantsHead: { minHeight: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  variantsTitle: { color: C.accent, fontSize: 12, fontWeight: '700' },
  variant: { minHeight: 36, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, borderTopWidth: 1, borderTopColor: C.borderSoft },
  variantName: { fontSize: 13, fontWeight: '600', flexShrink: 1 },
  actions: { flexDirection: 'row', gap: 8, alignItems: 'center' },
});
