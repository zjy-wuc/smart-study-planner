/** 纯装饰层：不参与布局、点击或统计数据计算。 */
export function StatisticsSky() {
  return (
    <div className="statistics-sky" aria-hidden="true">
      <span className="statistics-sky-sun" />
      <span className="statistics-sky-wisp" />
      <span className="statistics-sky-cloud statistics-sky-cloud--high" />
      <span className="statistics-sky-cloud statistics-sky-cloud--near" />
      <span className="statistics-sky-cloud statistics-sky-cloud--far" />
      <span className="statistics-sky-cloud statistics-sky-cloud--middle" />
      <span className="statistics-sky-cloud statistics-sky-cloud--low" />
    </div>
  );
}
