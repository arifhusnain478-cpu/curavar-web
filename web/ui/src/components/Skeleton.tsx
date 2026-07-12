// Loading skeletons — shown while the pipeline runs so the screen never sits
// empty or jumps. Shapes roughly match the real content they stand in for.

export function SkelLine({ w = "100%", h = 12 }: { w?: string; h?: number }) {
  return <span className="skel skel-line" style={{ width: w, height: h }} />;
}

export function ClassifySkeleton() {
  return (
    <div aria-busy="true" aria-label="Classifying">
      <div className="skel-card verdict-skel">
        <SkelLine w="42%" h={26} />
        <div className="skel-gauge">
          {Array.from({ length: 5 }).map((_, i) => (
            <span className="skel skel-cell" key={i} />
          ))}
        </div>
        <SkelLine w="70%" h={12} />
      </div>
      {Array.from({ length: 3 }).map((_, i) => (
        <div className="skel-card crit-skel" key={i}>
          <SkelLine w="18%" h={16} />
          <SkelLine w="90%" />
          <SkelLine w="75%" />
        </div>
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 4, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="ledger-wrap" aria-busy="true">
      <div className="tablescroll">
        <table>
          <tbody>
            {Array.from({ length: rows }).map((_, r) => (
              <tr key={r}>
                {Array.from({ length: cols }).map((_, c) => (
                  <td key={c}>
                    <SkelLine w={c === 0 ? "40%" : "80%"} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
