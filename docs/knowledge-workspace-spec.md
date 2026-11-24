# Knowledge workspace specification

**Approved product scope v0.1**

Build a private, self-hosted workspace where an EPITA team can write specifications, capture decisions, and find the context behind work tracked in Circular. The first milestone is a team wiki. Editable collections of pages are planned for the second milestone. Deployment will be planned separately after the product specification.

## First end-to-end workflow

A project lead creates a workspace for an event team and invites a teammate. The lead creates a **Launch plan** with a child page for **Registration**, documents a decision there, and links to the corresponding Circular ticket. The teammate searches for the decision, follows a link to a related page, and uses its backlinks to find the registration spec again. Before handing over the project, the lead exports the workspace as a folder of Markdown files.

| Product reference | Behavior to adopt |
| --- | --- |
| Notion pages and databases | Nest pages in a navigable hierarchy. If collections are included, each row opens as an ordinary page with a body and typed properties. [Notion databases](https://www.notion.com/help/intro-to-databases) |
| Obsidian internal links and backlinks | Type `[[` to find an existing page. Show which pages link to the current page. [Internal links](https://obsidian.md/help/links) · [Backlinks](https://obsidian.md/help/plugins/backlinks) |
| Obsidian Markdown vaults and Bases | Export readable Markdown files with relative links. Use the idea of multiple views over the same underlying pages if collections enter scope. [Data storage](https://obsidian.md/help/data-storage) · [Bases](https://obsidian.md/help/bases) |

## Milestone 1 requirements

| ID | Area | Required behavior |
| --- | --- | --- |
| DOC-01 | Navigation | A workspace has a page tree, a search entry point, and a reading/editing surface with breadcrumbs. Owners and editors can create root pages and child pages, rename pages, and move them to another parent in the same workspace. Within a parent, sort by title and then page ID. Duplicate titles are allowed. The server rejects cycles and keeps the page URL stable after rename or move. |
| DOC-02 | Editing | Support paragraphs, headings, bold, italic, links, inline code, ordered and unordered lists, task lists, quotes, and fenced code. Offer a visual editor and a Markdown source view. Both edit the same document. Save after a short pause and show Saving, Saved, or an error with Retry. Keep the draft available on a save failure and warn before leaving with unsaved changes. |
| DOC-03 | Links | Typing `[[` offers active pages in the current workspace with breadcrumbs to distinguish duplicates. Selecting a result inserts a link by stable page ID. Default labels derive from the target's current title. Custom labels remain as written. An explicit link creates one backlink per source page even when repeated. A trashed target displays as unavailable until restored. |
| DOC-04 | Search | Search active page titles and body text in workspaces the user can read. Match case-insensitively, show title matches first, and break ties by most recent update then page ID. Results show the title, workspace, breadcrumb, and a matching excerpt when available. An empty query shows no results. |
| DOC-05 | Sharing | Each workspace is private at creation. The owner invites an existing account as editor or viewer. The recipient must accept before gaining access. Roles apply to the entire workspace. Direct links, search, link suggestions, backlinks, and exports enforce the same server-side membership rules. |
| DOC-06 | History and trash | Each successful save of changed content records a revision and its author. Owners and editors can restore a previous revision as a new revision. Trash and restore operate on a page subtree atomically. Restoring a subtree whose former parent is unavailable places it at the workspace root. Active search, suggestions, and backlinks omit trashed pages. Trash retention and permanent deletion remain open decisions. |
| DOC-07 | Markdown export | Any current member can download a ZIP of active pages from a workspace. Use UTF-8 Markdown, preserve the page tree, and include a short stable ID suffix in filenames to prevent collisions. Rewrite internal page links to relative exported paths. Keep Circular and external URLs as URLs. |
| DOC-08 | Circular references | A user can paste a Circular ticket URL as an ordinary link. Store the URL and a user-authored label. Circular applies its existing ticket authorization on open. |

### Workspace permissions

| Action | Owner | Editor | Viewer |
| --- | --- | --- | --- |
| Read active pages, search, follow links, export | Yes | Yes | Yes |
| Create, edit, move, trash, or restore pages | Yes | Yes | |
| View and restore revisions, access trash | Yes | Yes | |
| Rename workspace, invite or remove members, change roles | Yes | | |

A pending invite grants zero document access. Revoking a membership takes effect on the next server request. Pages outside the caller's membership use the same response as missing pages. Ownership transfer, workspace deletion, and sharing individual pages require separate decisions.

## Technical design

- **Service architecture.** Design a separate web service around React/TypeScript, FastAPI, and PostgreSQL, following Circular’s stack. The identity provider remains open. Circular’s current registration checks the domain string and does not verify mailbox ownership.
- **Deployment deferred.** Decide hosting, environments, domains, operational ownership, rollout, and backup procedures in a later deployment plan. Circular’s deployment guide is a reference for that work. [Circular deployment](deployment.md)
- **Storage.** PostgreSQL is authoritative. Store workspace membership and invitations separately from pages. Each page has a stable ID, workspace ID, nullable parent ID, title, Markdown source, revision number, trash state, and timestamps. Store immutable body and title snapshots for revision history. Derive a link index from parsed internal links and update the page, revision, and index in a single transaction.
- **Editor contract.** Define a supported Markdown subset and a documented internal link form. Use `[](/pages/{id})` for an automatic label and `[Custom label](/pages/{id})` for a custom label, substituting the actual page ID for `{id}`. Treat links inside code as text. Reject an attempt to add a new internal link to a page outside the current workspace. If the visual editor cannot represent source content faithfully, keep it in source mode and give the user a clear explanation. Export writes a visible label for every internal link and rewrites its destination using the final path map. If a target is trashed or missing, export the label as plain text followed by ‘(page unavailable)’.
- **Concurrent saves.** Each write includes the revision last loaded or acknowledged by the client. A stale write returns HTTP 409. The client retains the draft and shows the latest saved copy alongside it so the user can reconcile changes. A save attempt carries a client-generated request ID. The server stores it with the successful result in the save transaction. After checking current access, a retry with the same request ID and payload returns that result without creating another revision. Reusing the request ID with different input returns HTTP 409.
- **Service boundary.** Circular owns ticket identity, content, and access. A later ticket preview or issue picker requires a separate identity and authorization contract. The URL link in DOC-08 supports independent deployment.
- **Scope for the pilot.** Browser use on desktop and mobile, private workspace access, Markdown authoring, and export. Revisit live co-editing, offline editing, attachments, comments, public links, and Obsidian import after selecting the first pilot workflow.

## Milestone 2 collections

Collections add a reusable schema to a set of pages. Start with a saved table view and property types for text, number, date, select, and checkbox. Users can add a page from the table, open an existing row as a page, edit typed values, and save column visibility, AND filters, and sort order per view. Views reference the same page IDs and values. A change in one view appears in every matching view, while deleting a view leaves the underlying pages intact. Collection permissions follow the workspace. Board views, relations, formulas, and embeddable views get their own scope decision. Circular remains the source for ticket status, assignment, and backlog.

## Acceptance scenarios

1. **Create and share.** An owner creates a workspace with a parent and child page. An invitee opening a direct child-page URL before acceptance sees the same result as an unknown page. The invitee accepts as viewer, can search and read the two pages, and receives a forbidden response on a write.
2. **Link, rename, and move.** Two branches each contain a page titled **Registration**. The picker distinguishes them by breadcrumb. After selecting one, renaming and moving its target keeps the link and its backlink intact. The other page gains no backlink.
3. **Protect concurrent edits.** Two editors load revision 3. The first save creates revision 4. The second sees a conflict, retains their draft, and can reconcile it against revision 4. A dropped response followed by a retry of the first save creates no extra revision.
4. **Trash and recover.** Trashing a parent removes its subtree from navigation and search. If a surviving page links into the subtree, the target is unavailable. Restoring recovers those links and backlinks. Attempting to move an ancestor into its descendant fails without modifying the tree.
5. **Export and open.** Export pages with duplicate titles, Unicode titles, and links in both directions. Extract the ZIP and follow both relative links. Verify that external and Circular URLs survive and trashed pages are absent.
6. **Revoke access.** After membership removal, a previously authorized user cannot open, search, link to, or export the workspace on the next request. A user with access to a linked doc still needs separate permission to open its Circular ticket.

## Open implementation decisions

| Decision | Current scope | Next detail to resolve |
| --- | --- | --- |
| Pilot team and weekly workflow | Write specs and decisions alongside Circular tickets. | Identify the first team and the real project it will use. |
| Identity | Separate docs service with ticket URL links in milestone 1. | Choose how accounts are provisioned and whether to use shared EPITA sign-in. |
| Obsidian interoperability | Markdown export in milestone 1. | Determine whether a vault migration is needed and which frontmatter, links, and attachments it must preserve. |
| Pilot operating limits | A private pilot team. | Confirm expected content volume, page limits, and history and trash retention. |
| Deployment | Deferred to a separate plan. | Decide hosting, environments, rollout, and operational ownership when deployment work begins. |
