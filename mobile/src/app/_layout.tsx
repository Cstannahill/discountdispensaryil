import { DarkTheme, ThemeProvider } from 'expo-router';
import { NativeTabs } from 'expo-router/native-tabs';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';

import { ToastHost } from '@/components/ui';
import { useLocationRefresh } from '@/hooks/use-location-refresh';
import { C } from '@/lib/theme';
import { hydrate, useAppState } from '@/state/store';

SplashScreen.preventAutoHideAsync();

const theme = { ...DarkTheme, colors: { ...DarkTheme.colors, background: C.bg, card: C.card, primary: C.accent, text: C.text, border: C.borderSoft } };

export default function RootLayout() {
  const ready = useAppState((s) => s.ready);
  const savedCount = useAppState((s) => s.saved.length);
  useEffect(() => { hydrate().finally(() => SplashScreen.hideAsync()); }, []);
  useLocationRefresh();
  if (!ready) return null;
  return (
    <ThemeProvider value={theme}>
      <StatusBar style="light" />
      <NativeTabs backgroundColor={C.card} tintColor={C.accent} indicatorColor={C.accentBg} iconColor={{ default: C.textMuted, selected: C.accent }} labelStyle={{ default: { color: C.textMuted }, selected: { color: C.accent } }}>
        <NativeTabs.Trigger name="index">
          <NativeTabs.Trigger.Label>Deals</NativeTabs.Trigger.Label>
          <NativeTabs.Trigger.Icon sf={{ default: 'tag', selected: 'tag.fill' }} md="sell" />
        </NativeTabs.Trigger>
        <NativeTabs.Trigger name="saved">
          <NativeTabs.Trigger.Label>Saved</NativeTabs.Trigger.Label>
          <NativeTabs.Trigger.Icon sf={{ default: 'star', selected: 'star.fill' }} md="star" />
          {savedCount > 0 && <NativeTabs.Trigger.Badge>{String(savedCount)}</NativeTabs.Trigger.Badge>}
        </NativeTabs.Trigger>
        <NativeTabs.Trigger name="stores">
          <NativeTabs.Trigger.Label>Stores</NativeTabs.Trigger.Label>
          <NativeTabs.Trigger.Icon sf={{ default: 'storefront', selected: 'storefront.fill' }} md="storefront" />
        </NativeTabs.Trigger>
        <NativeTabs.Trigger name="calculator">
          <NativeTabs.Trigger.Label>Calculator</NativeTabs.Trigger.Label>
          <NativeTabs.Trigger.Icon sf="percent" md="calculate" />
        </NativeTabs.Trigger>
      </NativeTabs>
      <ToastHost />
    </ThemeProvider>
  );
}
