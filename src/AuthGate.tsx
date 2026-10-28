import { useEffect, useState, type ReactNode } from 'react';
import { ArrowRight, LockKey, SignOut } from '@phosphor-icons/react';
import { api, ApiError, setCsrfToken, setWorkspaceId } from './api';
import type { AuthSession, User } from './types';
import { Dialog, ErrorMessage, message } from './ui';
import './account-features.css';

export function AuthGate({ children }: { children: (user: User, endSession: (notice?: string) => void, updateUser: (user: User) => void) => ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [attempt, setAttempt] = useState(0);
  function authenticated(value: AuthSession) {
    setCsrfToken(value.csrfToken);
    setSession(value);
    setNotice('');
  }
  function endSession(text = '') {
    setCsrfToken();
    setWorkspaceId();
    setSession(null);
    setNotice(text);
    history.replaceState(null, '', location.pathname);
  }
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    api.me().then(value => { if (active) authenticated(value); }).catch(error => {
      if (!active) return;
      if (!(error instanceof ApiError && error.status === 401)) setError(message(error));
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [attempt]);
  useEffect(() => {
    const expired = () => endSession('Votre session a expiré. Reconnectez-vous pour retrouver vos données enregistrées.');
    window.addEventListener('circular:session-expired', expired);
    return () => window.removeEventListener('circular:session-expired', expired);
  }, []);
  if (loading) return <main className="auth-shell"><div className="auth-card"><Brand /><p role="status">Ouverture de votre espace…</p></div></main>;
  if (error) return <main className="auth-shell"><div className="auth-card"><Brand /><h1>Connexion au serveur</h1><ErrorMessage>{error}</ErrorMessage><button className="button primary" onClick={() => setAttempt(value => value + 1)}>Réessayer</button></div></main>;
  if (session) return children(session.user, endSession, user => setSession(current => current ? { ...current, user } : current));
  return <LoginForm notice={notice} onAuthenticated={authenticated} />;
}

function Brand() { return <div className="auth-brand"><span className="brand-mark" aria-hidden="true" /><span>Circular</span></div>; }

function LoginForm({ notice, onAuthenticated }: { notice: string; onAuthenticated: (session: AuthSession) => void }) {
  const [register, setRegister] = useState(false);
  const [identifier, setIdentifier] = useState('');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  async function submit() {
    if (pending) return;
    setError('');
    if (register && password !== confirm) { setError('Les deux mots de passe doivent être identiques.'); return; }
    setPending(true);
    try { onAuthenticated(register ? await api.register(username.trim(), email.trim(), password) : await api.login(identifier.trim(), password)); }
    catch (error) { setError(message(error)); }
    finally { setPending(false); }
  }
  function switchMode() { setRegister(value => !value); setPassword(''); setConfirm(''); setError(''); }
  return <main className="auth-shell"><div className="auth-card"><Brand /><p className="auth-eyebrow">VOTRE ESPACE DE PROJET</p><h1>{register ? 'Créer un compte' : 'Se connecter'}</h1><p className="auth-intro">{register ? 'Créez vos projets privés et invitez les personnes avec qui vous travaillez.' : 'Retrouvez vos projets, vos tickets et votre équipe.'}</p>
    {notice && <p className="settings-notice" role="status">{notice}</p>}
    <form aria-busy={pending} onSubmit={event => { event.preventDefault(); void submit(); }}><fieldset disabled={pending}><ErrorMessage>{error}</ErrorMessage>
      {register ? <><label>Pseudo<input autoComplete="username" required minLength={2} maxLength={40} value={username} onChange={event => setUsername(event.target.value)} /></label><label>Adresse e-mail EPITA<input type="email" autoComplete="email" required maxLength={254} pattern="[^\s@]+@epita\.fr" value={email} onChange={event => setEmail(event.target.value)} placeholder="prenom.nom@epita.fr" /></label></> : <label>Pseudo ou adresse e-mail<input autoComplete="username" required maxLength={254} value={identifier} onChange={event => setIdentifier(event.target.value)} autoFocus /></label>}
      <label>Mot de passe<input type="password" autoComplete={register ? 'new-password' : 'current-password'} required minLength={register ? 12 : undefined} maxLength={128} value={password} onChange={event => setPassword(event.target.value)} aria-describedby={register ? 'password-help' : undefined} /></label>
      {register && <><p id="password-help" className="field-hint">12 à 128 caractères. Choisissez un mot de passe propre à Circular.</p><label>Confirmer le mot de passe<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={confirm} onChange={event => setConfirm(event.target.value)} /></label></>}
      <button className="button primary auth-submit" type="submit">{pending ? 'Connexion…' : register ? 'Créer mon compte' : 'Se connecter'}<ArrowRight size={17} aria-hidden="true" /></button>
    </fieldset></form><div className="auth-switch"><span>{register ? 'Vous avez déjà un compte ?' : 'Première visite ?'}</span><button className="button subtle" disabled={pending} onClick={switchMode}>{register ? 'Se connecter à mon compte' : 'Créer un compte'}</button></div><p className="auth-footnote">{register ? 'Réservé aux adresses @epita.fr. Aucun e-mail de vérification n’est envoyé pour le moment.' : 'Mot de passe oublié ? Contactez l’administrateur du service pour rétablir votre accès.'}</p>
  </div></main>;
}

export function AccountDialog({ user, onClose, onSessionEnd }: { user: User; onClose: () => void; onSessionEnd: (notice?: string) => void }) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const dirty = !!(currentPassword || password || confirm);
  async function changePassword() {
    if (pending) return;
    setError('');
    if (password !== confirm) { setError('Les deux nouveaux mots de passe doivent être identiques.'); return; }
    setPending(true);
    try { await api.changePassword(currentPassword, password); onSessionEnd('Mot de passe modifié. Reconnectez-vous avec votre nouveau mot de passe.'); }
    catch (error) { setError(message(error)); }
    finally { setPending(false); }
  }
  async function logout() {
    if (pending || (dirty && !window.confirm('Abandonner la saisie du mot de passe et se déconnecter ?'))) return;
    setError(''); setPending(true);
    try { await api.logout(); onSessionEnd('Vous êtes déconnecté.'); }
    catch (error) { setError(message(error)); }
    finally { setPending(false); }
  }
  return <Dialog title="Mon compte" onClose={onClose} dirty={dirty} pending={pending}><div className="form-body account-summary"><span className="account-avatar" aria-hidden="true">{(user.displayName || user.username)[0]?.toUpperCase()}</span><div><strong>{user.displayName || user.username}</strong><p>{user.email}</p></div><button className="button subtle" disabled={pending} onClick={() => void logout()}><SignOut size={17} />Se déconnecter</button></div><form onSubmit={event => { event.preventDefault(); void changePassword(); }} aria-busy={pending}><fieldset disabled={pending} className="form-body account-password"><h3><LockKey size={18} />Changer de mot de passe</h3><p className="field-hint">Vos sessions ouvertes seront fermées après le changement.</p><ErrorMessage>{error}</ErrorMessage><label>Mot de passe actuel<input type="password" autoComplete="current-password" required maxLength={128} value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} /></label><label>Nouveau mot de passe<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={password} onChange={event => setPassword(event.target.value)} /></label><label>Confirmer le nouveau mot de passe<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={confirm} onChange={event => setConfirm(event.target.value)} /></label><span className="field-hint">12 à 128 caractères.</span></fieldset><footer className="dialog-footer"><button type="submit" className="button primary" disabled={pending}>{pending ? 'Enregistrement…' : 'Changer le mot de passe'}</button></footer></form></Dialog>;
}
