import { useEffect, useState, type ReactNode } from 'react';
import { KeyboardAvoidingView, Modal, Pressable, ScrollView, StyleSheet, Text, View, type StyleProp, type TextStyle, type ViewStyle } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { C, MIN_TAP } from '@/lib/theme';
import { tap } from '@/lib/haptics';

export function Chip({ label, active, onPress, style }: { label: string; active?: boolean; onPress: () => void; style?: StyleProp<ViewStyle> }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!active }}
      onPress={() => { tap(); onPress(); }}
      style={({ pressed }) => [s.chip, active && s.chipOn, pressed && s.pressed, style]}>
      <Text style={[s.chipText, active && s.chipTextOn]}>{label}</Text>
    </Pressable>
  );
}

export function Badge({ children, color = C.textSoft, border = C.border, bg, style }: { children: ReactNode; color?: string; border?: string; bg?: string; style?: StyleProp<TextStyle> }) {
  return <Text style={[s.badge, { color, borderColor: border, backgroundColor: bg }, style]}>{children}</Text>;
}

export function Button({ label, onPress, kind = 'primary', style, disabled, a11y }: { label: string; onPress: () => void; kind?: 'primary' | 'ghost'; style?: StyleProp<ViewStyle>; disabled?: boolean; a11y?: string }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={a11y ?? label}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [s.btn, kind === 'primary' ? s.btnPrimary : s.btnGhost, pressed && s.pressed, disabled && { opacity: 0.5 }, style]}>
      <Text numberOfLines={1} style={[s.btnText, kind === 'primary' ? { color: C.accent } : { color: C.textSoft }]}>{label}</Text>
    </Pressable>
  );
}

/** A bottom sheet built on the native modal, so the system back gesture and screen readers treat it as a dialog. */
export function Sheet({ visible, title, onClose, children }: { visible: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const insets = useSafeAreaInsets();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose} statusBarTranslucent>
      <KeyboardAvoidingView behavior={process.env.EXPO_OS === 'ios' ? 'padding' : undefined} style={s.sheetWrap}>
        <Pressable style={s.backdrop} onPress={onClose} accessibilityLabel="Close" />
        <View style={[s.sheet, { paddingBottom: Math.max(insets.bottom, 16) }]}>
          <View style={s.sheetHead}>
            <Text style={s.sheetTitle} accessibilityRole="header">{title}</Text>
            <Pressable onPress={onClose} hitSlop={12} accessibilityRole="button" accessibilityLabel={`Close ${title}`}>
              <Text style={s.sheetClose}>Done</Text>
            </Pressable>
          </View>
          <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ gap: 16, paddingBottom: 8 }}>{children}</ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <View style={{ gap: 8 }}>
      <Text style={s.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

export const Row = ({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) => <View style={[s.row, style]}>{children}</View>;

// A minimal toast: one message at a time, announced to screen readers.
let pushToast: ((m: string) => void) | null = null;
export const toast = (m: string) => pushToast?.(m);
export function ToastHost() {
  const [msg, setMsg] = useState<string | null>(null);
  const insets = useSafeAreaInsets();
  useEffect(() => {
    let t: ReturnType<typeof setTimeout>;
    pushToast = (m) => { setMsg(m); clearTimeout(t); t = setTimeout(() => setMsg(null), 2600); };
    return () => { pushToast = null; clearTimeout(t); };
  }, []);
  if (!msg) return null;
  return (
    <View pointerEvents="none" style={[s.toastWrap, { bottom: insets.bottom + 96 }]}>
      <Text style={s.toast} accessibilityLiveRegion="polite" accessibilityRole="alert">{msg}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  pressed: { opacity: 0.65 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' },
  chip: { minHeight: 36, paddingHorizontal: 14, justifyContent: 'center', borderRadius: 18, borderWidth: 1, borderColor: C.border, backgroundColor: C.card },
  chipOn: { backgroundColor: C.accentBg, borderColor: C.accentBorder },
  chipText: { color: C.textSoft, fontSize: 13, fontWeight: '600' },
  chipTextOn: { color: C.accent },
  badge: { fontSize: 11, fontWeight: '600', paddingHorizontal: 7, paddingVertical: 2, borderRadius: 7, borderWidth: 1, overflow: 'hidden' },
  btn: { minHeight: MIN_TAP, paddingHorizontal: 12, borderRadius: 12, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  btnPrimary: { backgroundColor: C.accentBg, borderColor: C.accentBorder },
  btnGhost: { backgroundColor: C.cardAlt, borderColor: C.border },
  btnText: { fontSize: 13, fontWeight: '700' },
  sheetWrap: { flex: 1, justifyContent: 'flex-end' },
  backdrop: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.6)' },
  sheet: { maxHeight: '88%', backgroundColor: C.card, borderTopLeftRadius: 22, borderTopRightRadius: 22, borderWidth: 1, borderColor: C.border, paddingHorizontal: 16, paddingTop: 14 },
  sheetHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  sheetTitle: { color: C.text, fontSize: 18, fontWeight: '800' },
  sheetClose: { color: C.accent, fontSize: 16, fontWeight: '700' },
  sectionTitle: { color: C.textMuted, fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 },
  toastWrap: { position: 'absolute', left: 16, right: 16, alignItems: 'center' },
  toast: { color: C.text, backgroundColor: '#1e293b', borderColor: C.accentBorder, borderWidth: 1, borderRadius: 14, overflow: 'hidden', paddingHorizontal: 16, paddingVertical: 10, fontSize: 14, fontWeight: '600' },
});
