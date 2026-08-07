import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
  compact?: boolean;
}

interface State {
  error: Error | null;
}

/**
 * The app previously had no error boundary anywhere: an uncaught render
 * error (a failed 3D-model fetch when the backend is unreachable, a bad
 * WebGL context, a malformed API response) unmounts the whole React tree
 * by default, leaving a blank page with zero information - exactly what
 * "abre pero no se ve nada" looks like from the outside. This catches it
 * and shows something a user can act on and a developer can debug from.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("Axiscam UI crash:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      if (this.props.compact) {
        return (
          <div className="flex h-full min-h-[120px] flex-col items-center justify-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4 text-center">
            <AlertTriangle className="h-5 w-5 text-[var(--color-warn)]" />
            <p className="text-xs text-[var(--color-text-muted)]">No se pudo cargar este panel.</p>
            <button
              onClick={() => this.setState({ error: null })}
              className="text-xs font-medium text-[var(--color-accent)] hover:underline"
            >
              Reintentar
            </button>
          </div>
        );
      }

      return (
        <div className="flex h-dvh w-full flex-col items-center justify-center gap-4 bg-[var(--color-bg)] px-6 text-center">
          <AlertTriangle className="h-10 w-10 text-[var(--color-warn)]" />
          <div>
            <h1 className="text-lg font-semibold text-[var(--color-text)]">{this.props.fallbackTitle || "Algo salió mal"}</h1>
            <p className="mt-2 max-w-md text-sm text-[var(--color-text-muted)]">
              La interfaz encontró un error inesperado. Recarga la página - si sigue pasando, comparte el mensaje de
              abajo con soporte.
            </p>
          </div>
          <pre className="max-w-lg overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-left text-xs text-[var(--color-danger)]">
            {this.state.error.message}
          </pre>
          <button
            onClick={() => window.location.reload()}
            className="flex items-center gap-2 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-black"
          >
            <RefreshCw className="h-4 w-4" /> Recargar
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
