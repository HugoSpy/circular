import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import App from './App';
import { AuthGate } from './AuthGate';

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('Erreur de rendu', error, info.componentStack); }
  render() {
    return this.state.failed ? <main className="fatal-error"><h1>L’interface a rencontré une erreur</h1><p>Vos données sauvegardées sont conservées.</p><button onClick={() => location.reload()}>Recharger l’application</button></main> : this.props.children;
  }
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><ErrorBoundary><AuthGate>{(user, endSession) => <App key={user.id} user={user} onSessionEnd={endSession} />}</AuthGate></ErrorBoundary></React.StrictMode>);
