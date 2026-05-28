import React, { Component, ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(_error: Error): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    if (__DEV__) {
      console.error('[ErrorBoundary] Uncaught error:', error, info.componentStack);
    }
  }

  handleReset = () => {
    this.setState({ hasError: false });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <View style={styles.container}>
          <Text style={styles.emoji}>⚠️</Text>
          <Text style={styles.title}>Algo deu errado</Text>
          <Text style={styles.message}>
            O aplicativo encontrou um erro inesperado. Tente recarregar.
          </Text>
          <Text style={styles.detail}>Pressione "Tentar novamente" ou reinicie o aplicativo.</Text>
          <Pressable style={styles.btn} onPress={this.handleReset}>
            <Text style={styles.btnText}>Tentar novamente</Text>
          </Pressable>
        </View>
      );
    }
    return this.props.children;
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0F0F0F',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
  },
  emoji:   { fontSize: 48, marginBottom: 16 },
  title:   { fontSize: 20, fontWeight: '700', color: '#FFFFFF', marginBottom: 8, textAlign: 'center' },
  message: { fontSize: 14, color: '#9CA3AF', textAlign: 'center', lineHeight: 22, marginBottom: 12 },
  detail:  { fontSize: 11, color: '#4B5563', textAlign: 'center', marginBottom: 24, fontFamily: 'monospace' },
  btn:     { backgroundColor: '#39ff14', borderRadius: 12, paddingVertical: 12, paddingHorizontal: 28 },
  btnText: { color: '#0F0F0F', fontWeight: '700', fontSize: 15 },
});
