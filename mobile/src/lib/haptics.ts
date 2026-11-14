import * as Haptics from 'expo-haptics';

// Haptics are a nicety: never let a missing engine (web, old devices, low power mode) break an action.
const quiet = (p: Promise<unknown>) => { p.catch(() => {}); };
const native = process.env.EXPO_OS !== 'web';

export const tap = () => { if (native) quiet(Haptics.selectionAsync()); };
export const bump = () => { if (native) quiet(Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium)); };
export const success = () => { if (native) quiet(Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)); };
export const warning = () => { if (native) quiet(Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning)); };
