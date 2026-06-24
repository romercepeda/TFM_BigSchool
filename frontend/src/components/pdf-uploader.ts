import { BaseComponent } from './common/base-component.js';
import { t } from '../i18n/i18n.js';
import { uploadPdf } from '../api/analyses.js';

export class PdfUploader extends BaseComponent {
  private _holdingId = '';
  private _uploading = false;

  set holdingId(value: string) {
    this._holdingId = value;
  }

  protected render(): string {
    return `
      <style>
        :host { display: block; }
        .drop-zone {
          border: 2px dashed var(--color-border); border-radius: var(--radius-md);
          padding: var(--space-8); text-align: center; cursor: pointer;
          transition: border-color 0.15s, background 0.15s;
        }
        .drop-zone.over { border-color: var(--color-accent); background: var(--color-accent-light); }
        .hint { color: var(--color-text-muted); font-size: var(--font-size-sm); margin-top: var(--space-2); }
        input[type=file] { display: none; }
        .status { margin-top: var(--space-3); font-size: var(--font-size-sm); color: var(--color-text-secondary); }
        .error  { color: var(--color-danger); }
      </style>
      <div class="drop-zone" id="drop">
        <div>${this._uploading ? t('analysis.uploading') : t('analysis.drop_pdf')}</div>
        <div class="hint">${t('analysis.or_click')}</div>
        <input type="file" id="file-input" accept=".pdf" />
      </div>
      <div id="status" class="status"></div>
    `;
  }

  protected afterRender(): void {
    const drop = this.shadow.getElementById('drop')!;
    const input = this.shadow.getElementById('file-input') as HTMLInputElement;

    drop.addEventListener('click', () => input.click());
    drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('over'));
    drop.addEventListener('drop', (e) => {
      e.preventDefault();
      drop.classList.remove('over');
      const file = (e as DragEvent).dataTransfer?.files[0];
      if (file) void this._upload(file);
    });
    input.addEventListener('change', () => {
      const file = input.files?.[0];
      if (file) void this._upload(file);
    });
  }

  private async _upload(file: File): Promise<void> {
    const status = this.shadow.getElementById('status')!;
    this._uploading = true;
    this.shadow.innerHTML = this.render();
    try {
      const report = await uploadPdf(this._holdingId, file);
      status.textContent = t('analysis.upload_success');
      this.dispatchEvent(new CustomEvent('upload-complete', {
        detail: report, bubbles: true, composed: true,
      }));
    } catch (ex) {
      status.classList.add('error');
      status.textContent = (ex as Error).message;
    } finally {
      this._uploading = false;
    }
  }
}

customElements.define('pi-pdf-uploader', PdfUploader);
