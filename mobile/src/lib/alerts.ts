import AsyncStorage from '@react-native-async-storage/async-storage';

import { checkSaved, dropsToAnnounce, type Check, type Notified } from './saved-check';
import type { SavedDeal } from './types';

// Price-drop alerts without a server: the phone re-checks saved deals in the background a few times a day and posts
// a local notification. The operating system decides exactly when the check runs.
export const ALERT_TASK = 'ddil-price-drop-check';
const NOTIFIED_KEY = 'ddil.notified';
const STATE_KEY = 'ddil.state.v1';
const MIN_INTERVAL_MIN = 180; // menus sync four times a day
const CHANNEL = 'price-drops';

type Native = {
  Notifications: typeof import('expo-notifications');
  BackgroundTask: typeof import('expo-background-task');
  TaskManager: typeof import('expo-task-manager');
};

// The native modules are loaded lazily and defensively: in a build that lacks them (a browser, an older Expo Go)
// alerts are simply unavailable instead of crashing the app at launch.
let native: Native | null | undefined;
function load(): Native | null {
  if (native !== undefined) return native;
  if (process.env.EXPO_OS === 'web') return (native = null);
  try {
    native = { Notifications: require('expo-notifications'), BackgroundTask: require('expo-background-task'), TaskManager: require('expo-task-manager') };
  } catch { native = null; }
  return native;
}

export const alertsSupported = () => load() != null;

async function readNotified(): Promise<Notified> {
  try { return JSON.parse((await AsyncStorage.getItem(NOTIFIED_KEY)) || '{}'); } catch { return {}; }
}

/** Records drops the user has now seen on the Saved tab, so the background check does not announce them again. */
export async function markSeen(saved: readonly SavedDeal[], checks: Record<string, Check>): Promise<void> {
  try { await AsyncStorage.setItem(NOTIFIED_KEY, JSON.stringify(dropsToAnnounce(saved, checks, await readNotified()).notified)); } catch { /* best effort */ }
}

/** One background pass: check saved deals, notify about new drops. Returns how many notifications were posted. */
export async function runAlertCheck(): Promise<number> {
  const n = load();
  if (!n) return 0;
  const stored = JSON.parse((await AsyncStorage.getItem(STATE_KEY)) || '{}');
  const saved: SavedDeal[] = Array.isArray(stored.saved) ? stored.saved : [];
  if (!stored.alerts || !saved.length) return 0;
  const { alerts, notified } = dropsToAnnounce(saved, await checkSaved(saved), await readNotified());
  for (const a of alerts) {
    await n.Notifications.scheduleNotificationAsync({
      content: { title: a.title, body: a.body, data: { url: 'discountdispensaryil://saved', dealId: a.id }, ...(process.env.EXPO_OS === 'android' ? { channelId: CHANNEL } : {}) },
      trigger: null,
    });
  }
  await AsyncStorage.setItem(NOTIFIED_KEY, JSON.stringify(notified));
  return alerts.length;
}

/** Must run at app start, outside any component, so the system can wake the task when the app is closed. */
export function defineAlertTask(): void {
  const n = load();
  if (!n) return;
  try {
    if (n.TaskManager.isTaskDefined(ALERT_TASK)) return;
    n.TaskManager.defineTask(ALERT_TASK, async () => {
      try { await runAlertCheck(); return n.BackgroundTask.BackgroundTaskResult.Success; }
      catch { return n.BackgroundTask.BackgroundTaskResult.Failed; }
    });
    n.Notifications.setNotificationHandler({
      handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: false, shouldSetBadge: false }),
    });
  } catch { native = null; }
}

export type EnableResult = 'on' | 'denied' | 'restricted' | 'unsupported';

/** Asks for notification permission and schedules the background check. */
export async function enableAlerts(): Promise<EnableResult> {
  const n = load();
  if (!n) return 'unsupported';
  try {
    let perm = await n.Notifications.getPermissionsAsync();
    if (!perm.granted && perm.canAskAgain) perm = await n.Notifications.requestPermissionsAsync();
    if (!perm.granted) return 'denied';
    if (process.env.EXPO_OS === 'android') {
      await n.Notifications.setNotificationChannelAsync(CHANNEL, { name: 'Price drops', importance: n.Notifications.AndroidImportance.DEFAULT });
    }
    if ((await n.BackgroundTask.getStatusAsync()) === n.BackgroundTask.BackgroundTaskStatus.Restricted) return 'restricted';
    await n.BackgroundTask.registerTaskAsync(ALERT_TASK, { minimumInterval: MIN_INTERVAL_MIN });
    return 'on';
  } catch { return 'unsupported'; }
}

export async function disableAlerts(): Promise<void> {
  const n = load();
  if (!n) return;
  try { if (await n.TaskManager.isTaskRegisteredAsync(ALERT_TASK)) await n.BackgroundTask.unregisterTaskAsync(ALERT_TASK); } catch { /* already off */ }
}

/** Calls `open` when the user taps a price-drop notification, including the one that launched the app. */
export function onAlertTap(open: () => void): () => void {
  const n = load();
  if (!n) return () => {};
  try {
    const isOurs = (r: { notification: { request: { content: { data?: Record<string, unknown> | null } } } } | null) => !!r?.notification.request.content.data?.dealId;
    if (isOurs(n.Notifications.getLastNotificationResponse())) { n.Notifications.clearLastNotificationResponse(); open(); }
    const sub = n.Notifications.addNotificationResponseReceivedListener((r) => { if (isOurs(r)) open(); });
    return () => sub.remove();
  } catch { return () => {}; }
}
