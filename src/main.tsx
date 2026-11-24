import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import App from './App';
import { AuthGate } from './AuthGate';
import { WorkspaceGate } from './Workspaces';
import { McpConsent } from './McpConnect';

const mcpRequest = new URLSearchParams(location.hash.slice(1)).get('mcp');

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('Erreur de rendu', error, info.componentStack); }
  render() {
    return this.state.failed ? <main className="fatal-error"><h1>L’interface a rencontré une erreur</h1><p>Vos données sauvegardées sont conservées.</p><button onClick={() => location.reload()}>Recharger l’application</button></main> : this.props.children;
  }
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><ErrorBoundary><AuthGate mcpLogin={Boolean(mcpRequest)}>{(user, endSession, updateUser) => mcpRequest
  ? <McpConsent key={user.id} requestId={mcpRequest} user={user} />
  : <WorkspaceGate key={user.id} user={user} onUserUpdated={updateUser} onSessionEnd={endSession}>{controls => <App key={`${user.id}:${controls.workspace.id}`} user={user} onSessionEnd={endSession} onUserUpdated={updateUser} workspaceControls={controls} />}</WorkspaceGate>}</AuthGate></ErrorBoundary></React.StrictMode>);
