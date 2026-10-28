import { ArrowUpRight, CalendarBlank, PencilSimple, SquaresFour, Users } from '@phosphor-icons/react';
import { PROJECT_STATUS_NAMES, type Project } from './types';
import './ticket-features.css';

export function ProjectGrid({ projects, onOpen, onEdit, onMembers }: { projects: Project[]; onOpen: (id: number) => void; onEdit: (project: Project) => void; onMembers: (project: Project) => void }) {
  return <div className="project-grid">{projects.map(project => (
    <article key={project.id} data-testid={`project-card-${project.id}`} className="project-card">
      <button className="project-open" onClick={() => onOpen(project.id)} aria-label={`Ouvrir le projet ${project.name}`}>
        <div className="project-card-top"><span className="project-icon" style={{ color: project.color }}><SquaresFour size={22} /></span><span className="project-key">{project.key}</span><ArrowUpRight size={17} /></div>
        <h2>{project.name}</h2><p>{project.description || 'Aucune description pour ce projet.'}</p>
        <div className="project-plan"><span className={`project-status project-status-${project.status}`}>{PROJECT_STATUS_NAMES[project.status]}</span>{project.dueDate && <span className="project-due"><CalendarBlank size={14} aria-hidden="true" /><time dateTime={project.dueDate}>{new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(`${project.dueDate}T12:00:00`))}</time></span>}</div>
        <div className="project-progress"><span>{project.issueCount} ticket{project.issueCount !== 1 ? 's' : ''}</span><span>{project.doneCount} terminé{project.doneCount !== 1 ? 's' : ''}</span></div>
        <div className="progress-track"><span style={{ width: `${project.issueCount ? project.doneCount / project.issueCount * 100 : 0}%`, background: project.color }} /></div>
      </button>
      <div className="project-actions"><span className="project-key">{project.role === 'member' ? 'Partagé avec vous' : 'Votre projet'} · {project.issueCount ? Math.round(project.doneCount / project.issueCount * 100) : 0} % terminé</span><button className="project-access-button" aria-label={`Membres de ${project.name}`} onClick={() => onMembers(project)}><Users size={15} />Membres</button>{project.role === 'owner' && <button className="project-edit-button" data-focus-key={`project-edit-${project.id}`} aria-label={`Modifier ${project.name}`} onClick={() => onEdit(project)}><PencilSimple size={13} />Modifier</button>}</div>
    </article>
  ))}</div>;
}
