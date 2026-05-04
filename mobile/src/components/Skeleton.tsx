import React, { useEffect, useRef } from 'react';
import { Animated, DimensionValue, StyleSheet, View, ViewStyle } from 'react-native';
import { useTheme } from '../contexts/ThemeContext';

interface SkeletonBoxProps {
  width?: DimensionValue;
  height?: number;
  borderRadius?: number;
  style?: ViewStyle;
}

export function SkeletonBox({ width = '100%', height = 16, borderRadius = 8, style }: SkeletonBoxProps) {
  const { colors } = useTheme();
  const opacity = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.8, duration: 700, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.3, duration: 700, useNativeDriver: true }),
      ]),
    );
    animation.start();
    return () => animation.stop();
  }, []);

  return (
    <Animated.View
      style={[{ width, height, borderRadius, backgroundColor: colors.borderSubtle, opacity }, style]}
    />
  );
}

export function TournamentCardSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: colors.bgCard, borderColor: colors.borderSubtle }]}>
      <SkeletonBox height={18} width="70%" borderRadius={6} style={{ marginBottom: 8 }} />
      <SkeletonBox height={13} width="45%" borderRadius={5} style={{ marginBottom: 6 }} />
      <SkeletonBox height={13} width="55%" borderRadius={5} style={{ marginBottom: 12 }} />
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <SkeletonBox height={26} width={70} borderRadius={13} />
        <SkeletonBox height={26} width={60} borderRadius={13} />
        <SkeletonBox height={26} width={50} borderRadius={13} />
      </View>
    </View>
  );
}

export function TournamentListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <TournamentCardSkeleton key={i} />
      ))}
    </>
  );
}

export function ProfileSkeleton() {
  const { colors } = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: colors.bgCard, borderColor: colors.borderSubtle }]}>
      <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center' }}>
        <SkeletonBox width={48} height={48} borderRadius={24} />
        <View style={{ flex: 1, gap: 6 }}>
          <SkeletonBox height={16} width="60%" borderRadius={6} />
          <SkeletonBox height={12} width="40%" borderRadius={5} />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
  },
});
