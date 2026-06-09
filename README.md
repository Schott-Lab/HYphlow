# HYphlow

[![PyPI version](https://img.shields.io/pypi/v/hyphlow.svg)](https://pypi.org/project/hyphlow/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

HYphlow is a GUI-based bioinformatics pipeline that supports evolutionary selection pressure analysis using HyPhy. 
It provides a structured workflow for species label standardization, tree pruning, data reconciliation, branch annotation, batch HyPhy execution, and result extraction from HyPhy JSON output files.

---

## Table of Contents

* [Setup & Installation](#setup--installation)
* [Workflow & Usage](#workflow--usage) 
* [Supported HyPhy Models](#supported-hyphy-models)
* [Acknowledgements & Dependencies](#acknowledgements--dependencies)
* [Author & Credits](#author--credits)
* [Support & Contribution](#support--contribution) 
* [License](#license)

---

## Setup & Installation

HYphlow requires Python 3.8+ and [HyPhy](https://github.com/veg/hyphy). You can either install the required dependencies into an existing Conda environment or create a clean environment for HYphlow.

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

## Workflow & Usage

Once installed, verify the setup and launch the graphical interface by running:

```bash
hyphlow
```
---

The HYphlow interface guides users through four sequential modules that support data preparation, branch annotation, HyPhy execution, and result summarization. 

### 1. Data Preparation

Prepares standardized, and reconciled input files before evolutionary selection analysis.

* **Species Label Standardization:** Cross-references CSV metadata with the NCBI taxonomy database and standardizes FASTA headers and Newick leaf names. It extracts clean species or subspecies labels from longer sequence headers. 

* **Tree Pruning:** Generates gene-specific Newick trees by pruning a master species tree to match the taxa present in each FASTA alignment.

* **Data Reconciliation:** Checks for missing or mismatched taxa across CSV, FASTA, and Newick files.

### 2. Tree Annotation

Automates foreground branch annotation based on trait metadata.

* Identifies candidate foreground branches using parsimony and likelihood-based methods.
* Outputs foreground-annotated Newick trees and annotated SVG preview images.

### 3. HyPhy Execution

Supports batch execution of HyPhy analyses across multiple genes.

* Automatically matches FASTA alignments with their corresponding Newick trees.
* Configures CPU and thread settings for parallel execution.
* Generates an editable bash script for running selected HyPhy models.

### 4. Results Summary

Extracts and organizes results from HyPhy JSON output files.

* Allows users to drag and drop multiple HyPhy .json output files into the interface.
* Extracts key statistics such as p-values and LRT scores.
* Compiles extracted results into a single organized Excel workbook.

---

## Supported HyPhy Models

HYphlow currently supports data preparation, execution, and result summarization for the following models:

* **Gene-Level Models:** [BUSTED](https://help.datamonkey.org/methods/busted.html#references), [RELAX](https://help.datamonkey.org/methods/relax.html#relax-method-documentation)
* **Branch-Level Models:** [aBSREL](https://help.datamonkey.org/methods/absrel.html#absrel-adaptive-branch-site-random-effects-likelihood)
* **Site-Level Models:** [FEL](https://help.datamonkey.org/methods/fel.html#fixed-effects-likelihood-fel), [SLAC](https://help.datamonkey.org/methods/slac.html#single-likelihood-ancestor-counting-slac), [MEME](https://help.datamonkey.org/methods/meme.html#meme-mixed-effects-model-of-evolution), [FUBAR](https://help.datamonkey.org/methods/fubar.html#fast-unconstrained-bayesian-approximation-fubar)

---

## Acknowledgements & Dependencies

HYphlow is built using several open-source tools and libraries. If you use HYphlow in your research, please cite HYphlow alongside the relevant core software used in your analysis:

### Core Software
* **[HyPhy](https://github.com/veg/hyphy/):** Kosakovsky Pond, S. L., et al. (2020). HyPhy 2.5—A Customizable Platform for Evolutionary Hypothesis Testing Using Phylogenies. *Molecular Biology and Evolution*, 37(1), 295–299.
* **[ETE 3](https://etetoolkit.org/):** Huerta-Cepas, J., Serra, F., & Bork, P. (2016). ETE 3: Reconstruction, Analysis, and Visualization of Phylogenomic Data. *Molecular Biology and Evolution*, 33(6), 1635–1638. 
* **[pandas](https://pandas.pydata.org/):** The pandas development team. (2020). pandas-dev/pandas: Pandas [Computer software]. Zenodo.
* **[PyQt5](https://riverbankcomputing.com/software/pyqt/):** Riverbank Computing Limited. (2026). PyQt5: Python bindings for the Qt cross-platform application framework.

### Evolutionary Models
* **BUSTED:** Murrell, B., et al. (2015). Gene-Wide Identification of Episodic Selection. *Molecular Biology and Evolution*, 32(5), 1365–1371.
* **aBSREL:** Smith, M. D., et al. (2015). Less Is More: An Adaptive Branch-Site Random Effects Model for Evolutionary Trajectories. *Molecular Biology and Evolution*, 32(5), 1342–1353.
* **RELAX:** Wertheim, J. O., et al. (2015). RELAX: Detecting Relaxed Selection in a Phylogenetic Framework. *Molecular Biology and Evolution*, 32(3), 820–832.
* **FEL & SLAC:** Kosakovsky Pond, S. L., & Frost, S. D. W. (2005). Not So Different After All: A Comparison of Methods for Detecting Amino Acid Sites Under Selection. *Molecular Biology and Evolution*, 22(5), 1208–1222.
* **MEME:** Murrell, B., et al. (2012). Detecting Individual Sites Subject to Episodic Diversification. *PLoS Genetics*, 8(7), e1002764.
* **FUBAR:** Murrell, B., et al. (2013). FUBAR: A Fast, Unconstrained Bayesian AppRoximation for Inferring Selection. *Molecular Biology and Evolution*, 30(5), 1196–1205.
---

## Author & Credits

**HYphlow** was designed and developed by **Hyejung (Jay) Kwon** at the [Schott Lab: Evolution and Development of Vertebrate Visual Systems](https://www.yorku.ca/science/schott/), under the supervision of **Dr. Ryan K Schott**.

Logo designed by **Taegan Perez**.

Special thanks to the members of the **Schott Lab** for their feedback and support throughout the development of this project.

If you use this pipeline in your research, please link back to this repository and cite or acknowledge HYphlow where appropriate.

---
## Support & Contribution

Bug reports, feature requests, and code contributions are welcome through GitHub Issues and Pull Requests.

---

## License

HYphlow is distributed under the MIT License. See the `LICENSE` file for details.
