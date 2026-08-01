type Props = {
  open: boolean;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
};

export function CompanionAutomationConsent({
  open,
  message,
  onConfirm,
  onCancel,
}: Props) {
  if (!open) return null;

  return (
    <div className="companion-consent-backdrop" role="presentation">
      <div
        className="companion-consent-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="companion-consent-title"
        aria-describedby="companion-consent-body"
      >
        <h2 id="companion-consent-title" className="companion-consent-title">
          自动化操作确认
        </h2>
        <p id="companion-consent-body" className="companion-consent-body">
          {message}
        </p>
        <div className="companion-consent-actions">
          <button type="button" className="companion-consent-btn is-cancel" onClick={onCancel}>
            取消任务
          </button>
          <button type="button" className="companion-consent-btn is-confirm" onClick={onConfirm}>
            允许操作
          </button>
        </div>
      </div>
    </div>
  );
}
