import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ViewStyle, TextInput } from 'react-native';
import { Colors, Fonts, FontSizes, Radius, Spacing } from '../theme';

// ── Divider ───────────────────────────────────────────────────────────────────
export function Divider({ style }: { style?: ViewStyle }) {
  return <View style={[styles.divider, style]} />;
}

// ── SectionLabel ──────────────────────────────────────────────────────────────
export function SectionLabel({ text }: { text: string }) {
  return <Text style={styles.sectionLabel}>{text}</Text>;
}

// ── Card ──────────────────────────────────────────────────────────────────────
export function Card({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

// ── MonoBadge ─────────────────────────────────────────────────────────────────
export function MonoBadge({ text }: { text: string }) {
  return (
    <View style={styles.monoBadge}>
      <Text style={styles.monoBadgeText}>{text}</Text>
    </View>
  );
}

// ── Chip ──────────────────────────────────────────────────────────────────────
interface ChipProps {
  label:     string;
  variant:   'allowed' | 'blocked';
  onRemove?: (label: string) => void;
}

export function Chip({ label, variant, onRemove }: ChipProps) {
  const isAllowed = variant === 'allowed';
  return (
    <View style={[styles.chip, isAllowed ? styles.chipAllowed : styles.chipBlocked]}>
      <Text style={[styles.chipDot, isAllowed ? styles.chipAllowedText : styles.chipBlockedText]}>
        {isAllowed ? '●' : '⊘'}
      </Text>
      <Text style={[styles.chipLabel, isAllowed ? styles.chipAllowedText : styles.chipBlockedText]}>
        {label}
      </Text>
      {onRemove && (
        <TouchableOpacity onPress={() => onRemove(label)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
          <Text style={styles.chipRemove}>×</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

// ── ChipRow ───────────────────────────────────────────────────────────────────
interface ChipRowProps {
  items:     string[];
  variant:   'allowed' | 'blocked';
  onRemove?: (label: string) => void;
}

export function ChipRow({ items, variant, onRemove }: ChipRowProps) {
  if (items.length === 0) {
    return (
      <Text style={styles.emptyText}>
        {variant === 'allowed' ? 'Only browsers allowed right now' : 'No sites blocked yet'}
      </Text>
    );
  }
  return (
    <View style={styles.chipRow}>
      {items.map(item => (
        <Chip key={item} label={item} variant={variant} onRemove={onRemove} />
      ))}
    </View>
  );
}

// ── SubscriptionBadge ─────────────────────────────────────────────────────────
interface SubscriptionBadgeProps {
  status:       string | undefined;
  trialEndsAt:  string | null | undefined;
  onPress:      () => void;
}

export function SubscriptionBadge({ status, trialEndsAt, onPress }: SubscriptionBadgeProps) {
  let text  = '';
  let color: string = Colors.subTrial;

  if (status === 'lifetime') {
    text = 'Lifetime ✓'; color = Colors.subPremium;
  } else if (status === 'active') {
    text = 'Premium ✓'; color = Colors.subPremium;
  } else if (status === 'trialing' && trialEndsAt) {
    try {
      const ends     = new Date(trialEndsAt);
      const daysLeft = Math.max(0, Math.ceil((ends.getTime() - Date.now()) / 86400000));
      text  = `Trial · ${daysLeft}d left`;
      color = daysLeft <= 2 ? Colors.red : daysLeft <= 4 ? Colors.amber : Colors.subTrial;
    } catch {
      text = 'Trial'; color = Colors.subTrial;
    }
  } else if (['expired', 'cancelled', 'past_due', 'free'].includes(status ?? '')) {
    text = 'Upgrade →'; color = Colors.subUpgrade;
  } else {
    return null;
  }

  return (
    <TouchableOpacity onPress={onPress}>
      <Text style={[styles.subBadge, { color }]}>{text}</Text>
    </TouchableOpacity>
  );
}

// ── AddItemRow ────────────────────────────────────────────────────────────────
interface AddItemRowProps {
  placeholder:  string;
  onAdd:        (value: string) => void;
  buttonColor?: string;
  buttonLabel?: string;
}

export function AddItemRow({
  placeholder,
  onAdd,
  buttonColor = Colors.accent,
  buttonLabel = 'Add',
}: AddItemRowProps) {
  const [value, setValue] = React.useState('');

  const handleAdd = () => {
    const trimmed = value.trim().toLowerCase();
    if (!trimmed) return;
    onAdd(trimmed);
    setValue('');
  };

  return (
    <View style={addRowStyles.row}>
      <TextInput
        style={addRowStyles.input}
        value={value}
        onChangeText={setValue}
        placeholder={placeholder}
        placeholderTextColor={Colors.textMut}
        autoCapitalize="none"
        autoCorrect={false}
        onSubmitEditing={handleAdd}
        returnKeyType="done"
      />
      <TouchableOpacity
        style={[addRowStyles.btn, { backgroundColor: buttonColor }]}
        onPress={handleAdd}
        activeOpacity={0.8}
      >
        <Text style={addRowStyles.btnText}>{buttonLabel}</Text>
      </TouchableOpacity>
    </View>
  );
}

const addRowStyles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap:           8,
  },
  input: {
    flex:            1,
    backgroundColor: Colors.bgSurface,
    borderColor:     Colors.border,
    borderWidth:     1,
    borderRadius:    Radius.md,
    paddingHorizontal: Spacing.sm,
    height:          40,
    color:           Colors.textPri,
    fontFamily:      Fonts.sans,
    fontSize:        FontSizes.md,
  },
  btn: {
    borderRadius:   Radius.md,
    height:         40,
    paddingHorizontal: Spacing.md,
    justifyContent: 'center',
    alignItems:     'center',
  },
  btnText: {
    fontFamily: Fonts.sansBold,
    fontSize:   FontSizes.md,
    color:      Colors.textPri,
  },
});

// ── Styles ────────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  divider: {
    height:          1,
    backgroundColor: Colors.border,
    marginHorizontal: 0,
  },
  sectionLabel: {
    fontFamily:    Fonts.mono,
    fontSize:      FontSizes.xs,
    color:         Colors.textMut,
    letterSpacing: 0.5,
    paddingHorizontal: Spacing.lg,
    paddingTop:    Spacing.md,
    paddingBottom: 6,
  },
  card: {
    backgroundColor: Colors.bgSurface,
    borderColor:     Colors.border,
    borderWidth:     1,
    borderRadius:    Radius.md,
    padding:         Spacing.md,
  },
  monoBadge: {
    backgroundColor: '#1a1a2e',
    borderColor:     '#3333aa',
    borderWidth:     1,
    borderRadius:    Radius.sm,
    paddingHorizontal: 10,
    paddingVertical:   4,
  },
  monoBadgeText: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      '#5555cc',
  },
  chip: {
    flexDirection:  'row',
    alignItems:     'center',
    borderWidth:    1,
    borderRadius:   Radius.pill,
    paddingHorizontal: 10,
    paddingVertical:   4,
    gap:            5,
    margin:         3,
  },
  chipAllowed: {
    backgroundColor: Colors.chipAllowedBg,
    borderColor:     Colors.chipAllowedBorder,
  },
  chipBlocked: {
    backgroundColor: Colors.chipBlockedBg,
    borderColor:     Colors.chipBlockedBorder,
  },
  chipDot: {
    fontSize: FontSizes.xs,
  },
  chipLabel: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.sm,
  },
  chipAllowedText: { color: Colors.chipAllowedText },
  chipBlockedText: { color: Colors.chipBlockedText },
  chipRemove: {
    fontFamily: Fonts.sans,
    fontSize:   FontSizes.md,
    color:      Colors.textMut,
    marginLeft: 4,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap:      'wrap',
    marginTop:     4,
  },
  emptyText: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
    color:      Colors.textMut,
    paddingVertical: Spacing.sm,
  },
  subBadge: {
    fontFamily: Fonts.mono,
    fontSize:   FontSizes.xs,
  },
});