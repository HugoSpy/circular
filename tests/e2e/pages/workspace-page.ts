import { expect, type Page } from '@playwright/test';

export const accountPassword = 'Workspace-browser-passphrase-2026!';

export class WorkspacePage {
  constructor(readonly page: Page) {}
  get menuButton() { return this.page.getByRole('button', { name: 'Menu de l’espace', exact: true }); }
  get menu() { return this.page.getByRole('menu'); }

  async register(username: string) {
    await this.page.getByRole('button', { name: 'Créer un compte', exact: true }).click();
    await this.page.getByRole('textbox', { name: 'Pseudo', exact: true }).fill(username);
    await this.page.getByRole('textbox', { name: 'Adresse e-mail EPITA', exact: true }).fill(`${username}@epita.fr`);
    await this.page.getByLabel('Mot de passe', { exact: true }).fill(accountPassword);
    await this.page.getByLabel('Confirmer le mot de passe', { exact: true }).fill(accountPassword);
    await this.page.getByRole('button', { name: 'Créer mon compte', exact: true }).click();
    await expect(this.page.getByRole('heading', { name: 'Créer votre espace', exact: true })).toBeVisible();
  }

  async submitLogin(username: string) {
    await this.page.getByRole('textbox', { name: 'Pseudo ou adresse e-mail', exact: true }).fill(username);
    await this.page.getByLabel('Mot de passe', { exact: true }).fill(accountPassword);
    await this.page.getByRole('button', { name: 'Se connecter', exact: true }).click();
  }

  async login(username: string) {
    await this.submitLogin(username);
    await expect(this.menuButton).toBeVisible();
    await expect(this.page.getByRole('button', { name: 'Nouveau ticket', exact: true })).toBeEnabled();
  }

  async create(name: string, slug: string) {
    await expect(this.page.getByRole('heading', { name: 'Créer votre espace', exact: true })).toBeVisible();
    await this.page.getByRole('textbox', { name: 'Nom de l’espace', exact: true }).fill(name);
    await this.page.getByRole('textbox', { name: 'Identifiant de l’espace', exact: true }).fill(slug);
    await this.page.getByRole('button', { name: 'Créer l’espace', exact: true }).click();
  }

  async profile(name: string, title: string) {
    await expect(this.page.getByRole('heading', { name: 'Votre profil', exact: true })).toBeVisible();
    await this.page.getByRole('textbox', { name: 'Nom affiché', exact: true }).fill(name);
    await this.page.getByRole('textbox', { name: 'Titre ou rôle', exact: true }).fill(title);
    await this.page.getByRole('button', { name: 'Enregistrer et continuer', exact: true }).click();
    await expect(this.page.getByRole('heading', { name: 'Invitez votre équipe', exact: true })).toBeVisible();
  }

  async skipInvitations() {
    await expect(this.page.getByRole('heading', { name: 'Invitez votre équipe', exact: true })).toBeVisible();
    await this.page.getByRole('button', { name: 'Passer cette étape', exact: true }).click();
    await expect(this.page.getByRole('heading', { name: 'Vos outils, au même endroit', exact: true })).toBeVisible();
  }

  async finish() {
    await this.page.getByRole('button', { name: 'Ouvrir mon espace', exact: true }).click();
    await expect(this.menuButton).toBeVisible();
    await expect(this.page.getByRole('button', { name: 'Nouveau ticket', exact: true })).toBeEnabled();
  }

  async createAnother() {
    await this.menuButton.click();
    await this.page.getByRole('menuitem', { name: 'Créer un espace', exact: true }).click();
    await expect(this.page.getByRole('heading', { name: 'Créer votre espace', exact: true })).toBeVisible();
  }

  async switchTo(name: string) {
    await this.menuButton.click();
    await this.page.getByRole('menuitemradio', { name: `Ouvrir l’espace ${name}`, exact: true }).click();
    await expect(this.menuButton).toContainText(name);
  }

  async logout() {
    await this.menuButton.click();
    await this.page.getByRole('menuitem', { name: 'Se déconnecter', exact: true }).click();
    await expect(this.page.getByRole('heading', { name: 'Se connecter', exact: true })).toBeVisible();
  }
}
