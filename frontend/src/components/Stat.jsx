export default function Stat({label,value,tone=''}){return <div className="stat"><span>{label}</span><strong className={tone}>{value}</strong></div>}
