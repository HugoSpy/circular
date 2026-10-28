import { useState } from 'react';
import { ChatCenteredDots, Code, Info } from '@phosphor-icons/react';

/** Deliberately announced previews: no authorization, credentials or network calls. */
export function IntegrationsPanel() {
  const [notice, setNotice] = useState('');
  return <div className="integrations-panel">
    <p className="field-hint">Ces intégrations seront proposées prochainement. Votre espace est utilisable dès maintenant.</p>
    <div className="integration-cards">
      {[{ name: 'GitHub', Icon: Code, description: 'Relier vos tickets aux branches et aux pull requests.' }, { name: 'Slack', Icon: ChatCenteredDots, description: 'Retrouver les mises à jour de vos projets dans vos conversations.' }].map(({ name, Icon, description }) => <article className="integration-card" key={name}>
        <span className="integration-icon"><Icon size={25} aria-hidden="true" /></span>
        <div className="integration-heading"><h3>{name}</h3><span className="coming-soon">À venir</span></div>
        <p>{description}</p><button type="button" className="button" onClick={() => setNotice('Intégration pas encore implémentée')}>Configurer {name}</button>
      </article>)}
    </div>
    {notice && <p className="integration-notice" role="status"><Info size={18} aria-hidden="true" />{notice}</p>}
  </div>;
}
