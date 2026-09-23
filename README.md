# HYphlow

[![PyPI version](https://img.shields.io/pypi/v/hyphlow.svg)](https://pypi.org/project/hyphlow/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

HYphlow is a GUI-based bioinformatics pipeline for testing selection with HyPhy. It carries a dataset from raw species labels through to a summary spreadsheet:
standardizing species names against NCBI taxonomy, pruning, and reconciling trees against alignments, annotating foreground branches from trait data, running HyPhy in batches, and collecting the JSON results into one workbook.

The steps around a HyPhy run are usually done by hand, in a different way each time. HYphlow applies the same rules to every file, and records what it changed and what it left for the user to decide.

---

## Table of Contents

* [Setup & Installation](#setup--installation)
* [Input Files](#input-files)
* [Workflow & Usage](#workflow--usage) 
* [Supported HyPhy Models](#supported-hyphy-models)
* [Reference Data](#reference-data)
* [Citation](#citation)
* [Acknowledgements & Dependencies](#acknowledgements--dependencies)
* [Author & Credits](#author--credits)
* [Support & Contribution](#support--contribution) 
* [License](#license)

---

## Setup & Installation

HYphlow requires Python 3.10 or newer and [HyPhy](https://github.com/veg/hyphy). 

**HyPhy is not installed by pip.** It is distributed through bioconda, so the environment file below installs it alongside the Python dependencies. On Windows, HyPhy runs under WSL and HYphlow calls it there.


### Option 1: Existing Conda Environment

Use this option if you already have a Conda environment activated and want to add the required HYphlow dependencies:

```bash
conda env update -f https://raw.githubusercontent.com/hellojung0810/Schott_lab_HYphlow/refs/heads/main/environment.yml
```

```bash
pip install hyphlow
```

### Option 2: New Conda Environment

Use this option to create a clean environment for HYphlow:

```bash
conda env create -f https://raw.githubusercontent.com/hellojung0810/Schott_lab_HYphlow/refs/heads/main/environment.yml
```

```bash
conda activate hyphlow_env
```

```bash
pip install hyphlow
```

### Launch

```bash
hyphlow
```

---

## Input Files

| Input | Format | What it must satisfy |
|---|---|---|
| Alignment | FASTA (`.fasta`, `.fas`, `.fa`) | in-frame codon alignment; every sequence name appears once |
| Tree | Newick (`.nwk`, `.tre`, `.tree`) | tip names match the alignment |
| Trait data | CSV | one column of species names, one column per trait |

A name that appears twice in a FASTA file stops HyPhy before it writes any
result, so HYphlow reports the repeated name rather than passing the file on.
Taxa present in only one of the alignment and the tree are listed by name, and
the pair is left unchecked for the user to decide about.

---

## Workflow & Usage

The interface follows four steps. Each writes its output into the project
folder and records it in a manifest, so a later step can find what an earlier
one produced.

### 1. Data Preparation

* **Species Label Standardization** — Species names in a CSV are checked
  against NCBI taxonomy, and the matching FASTA headers and Newick tip labels
  are rewritten to one form. An exact match is applied automatically; a close
  match, a name that resolves above species level, and a provisional name such
  as *Testudo* sp. are each flagged for the user to accept or keep.
* **Tree Pruning** — A master species tree is pruned to the taxa present in
  each alignment, giving one tree per gene.
* **Data Reconciliation** — Taxa missing from the CSV, the alignment or the
  tree are listed, and the files can be brought to a shared set of taxa.

### 2. Tree Annotation

* Foreground branches are inferred from trait data by Fitch parsimony,
  Felsenstein likelihood, and the consensus of the two.
* Each step writes an annotated Newick tree and an SVG preview, so the branches
  a method selected can be seen before the analysis is run.

### 3. HyPhy Execution

* Alignments and trees are paired by the organism and gene shown in the
  interface, which the user can correct; whether a pair belongs together is
  then settled by comparing taxa, not file names.
* Analysis settings are written out in full rather than left to defaults, so a
  HyPhy version change cannot alter a result silently.
* CPU threads are divided between concurrent analyses, and the bash script is
  editable before it runs.
* The same jobs can be exported as a ZIP for another machine, or as a SLURM
  array script for a cluster.

### 4. Results Summary

* HyPhy JSON files are read into one workbook: one row per analysis on the
  summary sheet, with branch-level and site-level detail on their own sheets.
* Where an analysis was repeated to avoid a local optimum, the run with the
  lowest AIC-c is the one reported; the others stay in the AIC columns.
* Significance is decided by what each analysis tests — a gene-wide p-value for
  BUSTED and RELAX, a significant lineage for aBSREL, a significant site for
  FEL, MEME and FUBAR — rather than forced onto one number.

---


## Supported HyPhy Models

HYphlow currently supports data preparation, execution, and result summarization for the following models:

* **Gene-Level Models:** [BUSTED](https://help.datamonkey.org/methods/busted.html#references), [RELAX](https://help.datamonkey.org/methods/relax.html#relax-method-documentation)
* **Branch-Level Models:** [aBSREL](https://help.datamonkey.org/methods/absrel.html#absrel-adaptive-branch-site-random-effects-likelihood)
* **Site-Level Models:** [FEL](https://help.datamonkey.org/methods/fel.html#fixed-effects-likelihood-fel), [SLAC](https://help.datamonkey.org/methods/slac.html#single-likelihood-ancestor-counting-slac), [MEME](https://help.datamonkey.org/methods/meme.html#meme-mixed-effects-model-of-evolution), [FUBAR](https://help.datamonkey.org/methods/fubar.html#fast-unconstrained-bayesian-approximation-fubar)

---

## Reference Data

Species labels are checked against two sources.

| Source | Version | Used for |
|---|---|---|
| NCBI Taxonomy | downloaded by the user; the date of the dump in use is recorded in the validation report | confirming a species name, resolving a synonym, reporting the rank a name matched at |
| Organism name list | `organism_names_20260828.txt.gz`, shipped with the package | telling a species name from a gene symbol in a file name |

The NCBI taxonomy dump is not bundled: it is several hundred megabytes and NCBI
revises it continually. HYphlow reads it from `taxopy_db/` in the project
folder, or from the working directory. Because the dump changes, the date it
was downloaded belongs in the methods section of any paper using HYphlow.

---

## Citation

If you use HYphlow in your research, please cite it alongside HyPhy and the
models you ran:

> Kwon, H., & Schott, R. K. (2026). HYphlow: a GUI pipeline for phylogenetic
> selection analysis with HyPhy (Version 1.1.0) [Computer software].
> https://github.com/hellojung0810/Schott_lab_HYphlow

---

## Acknowledgements & Dependencies

HYphlow is built using several open-source tools and libraries. If you use HYphlow in your research, please cite HYphlow alongside the relevant core software used in your analysis:

### Core Software
* **[HyPhy](https://github.com/veg/hyphy/):** Kosakovsky Pond, S. L., et al. (2020). HyPhy 2.5—A Customizable Platform for Evolutionary Hypothesis Testing Using Phylogenies. *Molecular Biology and Evolution*, 37(1), 295–299.
* **[ETE 3](https://etetoolkit.org/):** Huerta-Cepas, J., Serra, F., & Bork, P. (2016). ETE 3: Reconstruction, Analysis, and Visualization of Phylogenomic Data. *Molecular Biology and Evolution*, 33(6), 1635–1638.
* **[NCBI Taxonomy](https://www.ncbi.nlm.nih.gov/taxonomy):** Schoch, C. L., et al. (2020). NCBI Taxonomy: a comprehensive update on curation, resources and tools. *Database*, 2020, baaa062.
* **[pandas](https://pandas.pydata.org/):** The pandas development team. (2020). pandas-dev/pandas: Pandas [Computer software]. Zenodo.
* **[PyQt5](https://riverbankcomputing.com/software/pyqt/):** Riverbank Computing Limited. (2026). PyQt5: Python bindings for the Qt cross-platform application framework.

### Evolutionary Models
* **BUSTED:** Murrell, B., et al. (2015). Gene-Wide Identification of Episodic Selection. *Molecular Biology and Evolution*, 32(5), 1365–1371.
* **aBSREL:** Smith, M. D., et al. (2015). Less Is More: An Adaptive Branch-Site Random Effects Model for Evolutionary Trajectories. *Molecular Biology and Evolution*, 32(5), 1342–1353.
* **RELAX:** Wertheim, J. O., et al. (2015). RELAX: Detecting Relaxed Selection in a Phylogenetic Framework. *Molecular Biology and Evolution*, 32(3), 820–832.
* **FEL:** Kosakovsky Pond, S. L., & Frost, S. D. W. (2005). Not So Different After All: A Comparison of Methods for Detecting Amino Acid Sites Under Selection. *Molecular Biology and Evolution*, 22(5), 1208–1222.
* **MEME:** Murrell, B., et al. (2012). Detecting Individual Sites Subject to Episodic Diversification. *PLoS Genetics*, 8(7), e1002764.
* **FUBAR:** Murrell, B., et al. (2013). FUBAR: A Fast, Unconstrained Bayesian AppRoximation for Inferring Selection. *Molecular Biology and Evolution*, 30(5), 1196–1205.
---

## Author & Credits

**HYphlow** was designed and developed by **Hyejung (Jay) Kwon** at the [Schott Lab: Evolution and Development of Vertebrate Visual Systems](https://www.yorku.ca/science/schott/), under the supervision of **Dr. Ryan K Schott**.

Logo designed by **Taegan Perez**.

Special thanks to the members of the **Schott Lab** for their feedback and support throughout the development of this project.

---
## Support & Contribution

Bug reports, feature requests, and code contributions are welcome through GitHub Issues and Pull Requests.

---

## License

HYphlow is distributed under the MIT License. See the `LICENSE` file for details.
