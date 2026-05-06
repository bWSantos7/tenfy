import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  /** Optional custom fallback UI. Receives the caught error. */
  fallback?: (error: Error) => ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * ErrorBoundary — catches rendering errors in child subtree.
 * Wrap expensive/dynamic sections (e.g., AdminPanelPage tabs) with this to
 * prevent a single chart or data error from crashing the whole app.
 *
 * Usage:
 *   <ErrorBoundary>
 *     <SomeDangerousComponent />
 *   </ErrorBoundary>
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // In production, replace this with your monitoring SDK (e.g. Sentry.captureException)
    console.error('[ErrorBoundary] Caught rendering error:', error, info.componentStack);
  }

  reset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (this.state.hasError && this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback(this.state.error);
      }

      return (
        <div className="card text-center py-10 space-y-3">
          <p className="text-sm font-semibold text-text-primary">Algo deu errado ao carregar esta seção.</p>
          <p className="text-xs text-text-muted">Por favor, recarregue a página ou contate o suporte se o erro persistir.</p>
          <button
            onClick={this.reset}
            className="btn-secondary text-xs !py-1.5 !px-4"
          >
            Tentar novamente
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
