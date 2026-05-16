"use strict";

/*
 * Keim Agenten-Zweige Web-Adapter
 *
 * Dieser Adapter ist bewusst klein, deterministisch und ohne eval/Function.
 * Er spiegelt exakt den geprüften Keim-Rechenkern aus src/main.keim:
 *
 *   agent_basis(zweig)      = 1 + zweig
 *   agent_quadrat(wert)     = wert * wert
 *   agent_zweig(zweig)      = agent_quadrat(agent_basis(zweig))
 *   agent_batch_summe_10()  = Summe agent_zweig(1..10)
 *
 * Die Web-Ansicht ist damit eine dokumentierte Visualisierung, keine versteckte
 * JavaScript-Geschäftslogik mit freier Ausdrucksauswertung.
 */

const KeimAgentenAdapter = Object.freeze({
  agentBasis(zweig) {
    const z = Number(zweig);
    if (!Number.isInteger(z) || z < 1 || z > 10) {
      throw new Error("Zweig muss eine ganze Zahl von 1 bis 10 sein.");
    }
    return 1 + z;
  },

  agentQuadrat(wert) {
    const w = Number(wert);
    if (!Number.isInteger(w)) {
      throw new Error("Wert muss ganzzahlig sein.");
    }
    return w * w;
  },

  branch(zweig) {
    const basis = this.agentBasis(zweig);
    return {
      zweig: Number(zweig),
      basis,
      quadrat: this.agentQuadrat(basis)
    };
  },

  allBranches() {
    const out = [];
    for (let z = 1; z <= 10; z += 1) {
      out.push(this.branch(z));
    }
    return out;
  },

  batchSum10() {
    let summe = 0;
    for (const item of this.allBranches()) {
      summe += item.quadrat;
    }
    return summe;
  }
});
