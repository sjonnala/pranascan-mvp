import React, { ReactNode, useEffect, useRef } from 'react';
import { Animated, Easing, StyleProp, ViewStyle } from 'react-native';

interface PranaPulseRevealProps {
  children: ReactNode;
  delay?: number;
  distance?: number;
  duration?: number;
  scaleFrom?: number;
  style?: StyleProp<ViewStyle>;
}

export function PranaPulseReveal({
  children,
  delay = 0,
  distance = 18,
  duration = 480,
  scaleFrom = 0.98,
  style,
}: PranaPulseRevealProps) {
  const opacity = useRef(new Animated.Value(0)).current;
  const translateY = useRef(new Animated.Value(distance)).current;
  const scale = useRef(new Animated.Value(scaleFrom)).current;

  useEffect(() => {
    opacity.setValue(0);
    translateY.setValue(distance);
    scale.setValue(scaleFrom);

    const animation = Animated.parallel([
      Animated.timing(opacity, {
        toValue: 1,
        duration,
        delay,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
      Animated.timing(translateY, {
        toValue: 0,
        duration,
        delay,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
      Animated.timing(scale, {
        toValue: 1,
        duration,
        delay,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
    ]);

    animation.start();
    return () => {
      animation.stop();
    };
  }, [delay, distance, duration, opacity, scale, scaleFrom, translateY]);

  return (
    <Animated.View
      style={[
        style,
        {
          opacity,
          transform: [{ translateY }, { scale }],
        },
      ]}
    >
      {children}
    </Animated.View>
  );
}
