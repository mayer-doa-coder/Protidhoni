import {useEffect, useMemo, useRef} from 'react';
import {Animated, Pressable, StyleSheet, View} from 'react-native';

import {useLanguage} from '../i18n/LanguageContext';
import {AppText} from '../ui/AppText';
import {colors, radius, spacing} from '../ui/theme';

const AUTO_DISMISS_MS = 5000;
const RING_SIZES = [206, 250, 294, 340];

/** Ed25519-authenticated peers this device is currently connected to, laid
 * out on a circle around the pulsing SOS indicator -- the real mesh-relay
 * equivalent of the Figma reference's illustrative contact bubbles. */
function orbitPosition(index: number, total: number, radiusPx: number) {
  const angle = (index / Math.max(total, 1)) * Math.PI * 2 - Math.PI / 2;
  return {
    left: Math.cos(angle) * radiusPx,
    top: Math.sin(angle) * radiusPx,
  };
}

export function SosCallingScreen({
  connectedPeerNames,
  onDone,
}: {
  connectedPeerNames: readonly string[];
  onDone: () => void;
}) {
  const {t} = useLanguage();
  const pulse = useRef(new Animated.Value(0)).current;
  const peers = useMemo(() => connectedPeerNames.slice(0, 6), [connectedPeerNames]);

  useEffect(() => {
    const loop = Animated.loop(
      Animated.timing(pulse, {toValue: 1, duration: 1800, useNativeDriver: true}),
    );
    loop.start();
    const dismiss = setTimeout(onDone, AUTO_DISMISS_MS);
    return () => {
      loop.stop();
      clearTimeout(dismiss);
    };
  }, [onDone, pulse]);

  return (
    <View style={styles.page}>
      <AppText style={styles.title}>{t('home.calling.title')}</AppText>
      <AppText style={styles.body}>{t('home.calling.body')}</AppText>

      <View style={styles.stage}>
        {RING_SIZES.map(size => (
          <Animated.View
            key={size}
            style={[
              styles.ring,
              {
                width: size,
                height: size,
                borderRadius: size / 2,
                opacity: pulse.interpolate({
                  inputRange: [0, 0.5, 1],
                  outputRange: [0.55, 0.15, 0.55],
                }),
                transform: [
                  {
                    scale: pulse.interpolate({inputRange: [0, 1], outputRange: [0.94, 1.04]}),
                  },
                ],
              },
            ]}
          />
        ))}
        <View style={styles.core}>
          <AppText style={styles.coreText}>SOS</AppText>
        </View>
        {peers.map((name, index) => {
          const {left, top} = orbitPosition(index, peers.length, 150);
          return (
            <View key={name} style={[styles.peerBubble, {left: left - 18 + 150, top: top - 18 + 150}]}>
              <View style={styles.peerAvatar}>
                <AppText style={styles.peerAvatarText}>{name.slice(0, 1).toUpperCase()}</AppText>
              </View>
              <AppText style={styles.peerName} numberOfLines={1}>
                {name}
              </AppText>
            </View>
          );
        })}
      </View>

      <AppText style={styles.status}>
        {peers.length > 0
          ? t('home.calling.relayedTo', {count: String(peers.length)})
          : t('home.calling.waiting')}
      </AppText>

      <Pressable accessibilityRole="button" onPress={onDone} style={styles.doneButton} testID="sos-calling-done">
        <AppText style={styles.doneButtonText}>{t('home.calling.done')}</AppText>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: colors.surface, alignItems: 'center', paddingTop: 72, paddingHorizontal: spacing.lg},
  title: {color: colors.ink, fontSize: 22, fontWeight: '700'},
  body: {color: colors.inkMuted, fontSize: 14, textAlign: 'center', marginTop: spacing.sm, lineHeight: 20},
  stage: {width: 340, height: 340, alignItems: 'center', justifyContent: 'center', marginTop: spacing.xl},
  ring: {position: 'absolute', backgroundColor: colors.primary},
  core: {
    width: 140,
    height: 140,
    borderRadius: 70,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 10,
    borderColor: colors.surface,
  },
  coreText: {color: colors.surface, fontSize: 30, fontWeight: '800'},
  peerBubble: {position: 'absolute', width: 60, alignItems: 'center', gap: 2},
  peerAvatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.ink,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: colors.surface,
  },
  peerAvatarText: {color: colors.surface, fontWeight: '700', fontSize: 13},
  peerName: {color: colors.ink, fontSize: 9, fontWeight: '600'},
  status: {color: colors.inkMuted, fontSize: 13, marginTop: spacing.xl, textAlign: 'center'},
  doneButton: {
    marginTop: spacing.xl,
    backgroundColor: colors.background,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
  },
  doneButtonText: {color: colors.ink, fontWeight: '700'},
});
