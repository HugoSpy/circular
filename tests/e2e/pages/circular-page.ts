import type { Locator, Page } from '@playwright/test';

export type IssueDraft = {
  title: string;
  description?: string;
  project?: string;
  status?: string;
  priority?: string;
};

export class CircularPage {
  constructor(readonly page: Page) {}
  get newTicketDialog() { return this.page.getByRole('dialog', { name: 'Nouveau ticket', exact: true }); }
  get projectDialog() { return this.page.getByRole('dialog', { name: 'Nouveau projet', exact: true }); }
  get detail() { return this.page.getByRole('dialog'); }
  get search() { return this.page.getByRole('searchbox', { name: 'Rechercher des tickets' }); }
  get projectFilter() { return this.page.getByRole('combobox', { name: 'Filtrer par projet', exact: true }); }
  get statusFilter() { return this.page.getByRole('combobox', { name: 'Filtrer par statut', exact: true }); }
  get priorityFilter() { return this.page.getByRole('combobox', { name: 'Filtrer par priorité', exact: true }); }
  get rows() { return this.page.getByTestId(/^issue-row-/); }
  row(title: string) { return this.rows.filter({ has: this.page.getByText(title, { exact: true }) }); }
  card(title: string) { return this.page.getByTestId(/^issue-card-/).filter({ has: this.page.getByText(title, { exact: true }) }); }
  column(status: string) { return this.page.getByTestId(`board-column-${status}`); }

  async createProject(name: string, key: string) {
    const navigation = this.page.getByRole('navigation', { name: 'Navigation principale' });
    await navigation.getByRole('button', { name: /^Projets/ }).click();
    await this.page.getByRole('main').getByRole('button', { name: 'Nouveau projet', exact: true }).click();
    await this.projectDialog.getByRole('textbox', { name: 'Nom du projet', exact: true }).fill(name);
    await this.projectDialog.getByRole('textbox', { name: 'Préfixe', exact: true }).fill(key);
    await this.projectDialog.getByRole('button', { name: 'Créer le projet', exact: true }).click();
    await this.projectDialog.waitFor({ state: 'hidden' });
    await navigation.getByRole('button', { name: /^Tous les tickets/ }).click();
  }
  async fillTicket(dialog: Locator, draft: IssueDraft) {
    await dialog.getByRole('textbox', { name: 'Titre', exact: true }).fill(draft.title);
    if (draft.description !== undefined) await dialog.getByRole('textbox', { name: 'Description', exact: true }).fill(draft.description);
    if (draft.project !== undefined) await dialog.getByRole('combobox', { name: 'Projet', exact: true }).selectOption({ label: draft.project });
    if (draft.status !== undefined) await dialog.getByRole('combobox', { name: 'Statut', exact: true }).selectOption(draft.status);
    if (draft.priority !== undefined) await dialog.getByRole('combobox', { name: 'Priorité', exact: true }).selectOption(draft.priority);
  }
  async createTicket(draft: IssueDraft) {
    await this.page.getByRole('button', { name: 'Nouveau ticket', exact: true }).click();
    await this.fillTicket(this.newTicketDialog, draft);
    await this.newTicketDialog.getByRole('button', { name: 'Créer le ticket', exact: true }).click();
    await this.newTicketDialog.waitFor({ state: 'hidden' });
  }
  async openTicket(title: string) { await this.row(title).click(); }
  async saveTicket(draft: IssueDraft) {
    await this.fillTicket(this.detail, draft);
    await this.detail.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  }
  async closeDetail() { await this.detail.getByRole('button', { name: 'Fermer', exact: true }).click(); }
  async comment(body: string) {
    await this.detail.getByRole('textbox', { name: 'Ajouter un commentaire', exact: true }).fill(body);
    await this.detail.getByRole('button', { name: 'Publier le commentaire', exact: true }).click();
  }
  async board() { await this.page.getByRole('button', { name: 'Tableau', exact: true }).click(); }
  async list() { await this.page.getByRole('button', { name: 'Liste', exact: true }).click(); }
}
