import { BookOpen, ExternalLink, ShieldCheck } from "lucide-react";

export function ChatUseGuide({
  onOpenSettings,
}: {
  onOpenSettings?: () => void;
}) {
  return (
    <details className="chatUseGuide">
      <summary>
        <BookOpen size={19} />
        <span>How to use in chat</span>
      </summary>
      <div className="chatUseInstructions">
        <p>
          Keep Reweave open and use its Chrome or Edge extension in ChatGPT or
          Claude.
        </p>
        <ol>
          <li>
            Open the conversation you want to continue and write your request in
            the message box.
          </li>
          <li>
            Open the Reweave extension and choose the destination scope for this
            conversation.
          </li>
          <li>
            Press <strong>Use Reweave</strong>. Allowed, relevant context is
            added to your existing draft.
          </li>
          <li>
            Read the added context, edit if needed, then send the message
            yourself.
          </li>
        </ol>
        <p className="trustNote">
          <ShieldCheck size={17} /> Nothing is inserted or submitted by opening
          this guide. Save and Use are separate, explicit actions.
        </p>
        {onOpenSettings && (
          <button
            type="button"
            className="contextTextButton"
            onClick={onOpenSettings}
          >
            Extension setup &amp; connection <ExternalLink size={15} />
          </button>
        )}
      </div>
    </details>
  );
}
