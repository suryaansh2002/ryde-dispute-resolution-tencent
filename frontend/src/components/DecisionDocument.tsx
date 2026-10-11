import Markdown from 'react-markdown'

export function DecisionDocument({ markdown }: { markdown: string }) {
  return (
    <div className="doc">
      <Markdown>{markdown}</Markdown>
    </div>
  )
}
