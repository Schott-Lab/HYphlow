# Schott_lab_HYphlow

## Table of Contents
* [Overview](#overview)
* [Data Preparation](#data-preparation)
  * [Species Label Standardization](#species-label-standardization)
  * [Tree Pruning](#tree-pruning)
  * [Data Reconciliation](#data-reconciliation)
* [Tree Annotation](#tree-annotation)
* [HyPhy Execution](#hyphy-execution)
* [Results Summary](#results-summary)
* [Supported HyPhy Models](#supported-hyphy-models)
* [Dependencies](#dependencies)

---

## Overview
HYphlow is a streamlined pipeline designed to automate and manage HyPhy analyses for multiple genes, from execution to result summarization.

---

## Data Preparation

### Species Label Standardization
*(Documentation for this sub-module goes here)*

### Tree Pruning
*(Documentation for this sub-module goes here)*

### Data Reconciliation
The Data Reconciliation module checks and standardizes species labels across CSV, FASTA, and Newick tree files.

When preparing comparative or phylogenetic analyses, species names often appear in different formats across input files. For example, the same species may appear with extra sequence IDs in FASTA headers, different spellings in CSV files, or inconsistent labels in Newick trees. This module helps identify and correct these mismatches before running downstream analyses.

**Key Features**
* **Checks species names** in CSV files against the NCBI taxonomy database.
* **Standardizes FASTA headers** into species-level labels.
* **Standardizes Newick tree leaf names** into species-level labels.
* **Compares species labels** across CSV, FASTA, and Newick files.
* **Identifies missing or mismatched taxa** between input files.
* **Supports automatic correction** for similar species names when possible.
* **Generates cleaned input files** for downstream analysis.
* **Saves validation and reconciliation reports** for review.

**Input**
Use CSV, FASTA, and Newick tree files that contain overlapping species labels. 
For FASTA and NWK files, it is recommended to use the formatted outputs generated from the previous Data Preparation steps.
```text
trait_data.csv
GeneName_aln_fmt_v1_MMDD.fasta
GeneName_tree_fmt_v1_MMDD.nwk
```

The CSV file should include a species column.
```text
species,trait
Species_A,nocturnal
Species_B,diurnal
Species_C,nocturnal
```

The FASTA file may contain longer sequence headers.
```text
>Species_A_gene1
ATGCGT...
>Species_B_gene1
ATGCGT...
```

The Newick tree should contain matching species labels.
```text
(Species_A,Species_B,Species_C);
```

**Output**
The module generates standardized files and detailed Excel reconciliation reports.
```text
GeneName_aln_rec_v1_MMDD.fasta
GeneName_tree_rec_v1_MMDD.nwk
Rpt_GeneName_Reconciliation_Details_MMDD.xlsx
```
These cleaned files can be used directly in the Tree Annotation and HyPhy Execution modules.

---

## Tree Annotation
The Tree Annotation module uses CSV trait data to automatically add foreground labels (`{FG}`) to a Newick tree file.

When preparing HyPhy analyses, users often need to manually decide which branches should be treated as foreground branches. This module helps automate that step by comparing trait information across the tree and generating a foreground-annotated Newick file based on ancestral state reconstruction.

**Key Features**
* **Uses CSV trait data** and a matching Newick tree file automatically.
* **Allows users to choose** the target trait columns and foreground phenotypic values.
* **Identifies candidate foreground branches** using Fitch, Sankoff, and Felsenstein ML algorithms.
* **Generates scalable preview images (SVG)** for each method and the final consensus.
* **Saves a foreground-annotated** Newick file ready for HyPhy execution.
* **Exports a detailed CSV report** scoring internal nodes.

**Supported Annotation Methods**
Currently supported methods include:
* Fitch parsimony
* Sankoff parsimony
* Felsenstein likelihood
* Strict Consensus

**Input**
Use a trait CSV file and a matching reconciled Newick tree file:
```text
trait_data.csv
GeneName_tree_rec_v1_MMDD.nwk
```

Example CSV format:
```text
species,trait
Species_A,nocturnal
Species_B,nocturnal
Species_C,diurnal
Species_D,diurnal
```

**Output**
The module generates an annotated Newick tree, preview images, and a report:
```text
GeneName_tree_annotated_Strict_Consensus.nwk
GeneName_tree_annotated_figure.svg
Rpt_GeneName_tree_annotated_MMDD.csv
```
The annotated Newick tree can be used directly in the HyPhy Execution module.

---

## HyPhy Execution
The HyPhy Execution module generates and runs batch HyPhy analysis scripts using matched FASTA alignment files and Newick tree files. 

When analyzing multiple genes, users often need to prepare separate HyPhy commands for each alignment and tree pair. This module reduces that manual work by matching input files, generating execution scripts, and supporting parallel HyPhy analyses.

**Key Features**
* **Matches FASTA alignment files** with corresponding Newick tree files automatically.
* **Supports batch execution** of multiple HyPhy analyses in parallel.
* **Supports both all-branch** analysis and foreground-branch analysis.
* **Generates an editable** HyPhy execution bash script.
* **Allows users to adjust CPU/thread** settings before running analyses.
* **Checks input files** before execution and reports potential file-matching issues.
* **Saves HyPhy output files** and detailed log reports for downstream review.

**Input**
Use matched FASTA alignment files and Newick tree files:
```text
GeneName_aln_rec_v1_MMDD.fasta
GeneName_tree_rec_v1_MMDD.nwk
```

For foreground-branch analyses, use Newick tree files that contain foreground branch labels (`{FG}`):
```text
GeneName_tree_annotated_Strict_Consensus.nwk
```

**Output**
The module generates HyPhy JSON result files and individual log reports:
```text
GeneName_aln_rec_v1_MMDD_BUSTED.json
GeneName_aln_rec_v1_MMDD_BUSTED_log.txt
```

---

## Results Summary
The Results Summary module extracts key results from HyPhy `.json` output files and saves them into a single Excel summary file.

When running HyPhy analyses for multiple genes, users often need to open many JSON files manually to check p-values, LRT scores, and significant branches. This module reduces that manual work by collecting the main results automatically.

**Key Features**
* **Drag and drop** HyPhy `.json` result files directly into the interface.
* **Detects the HyPhy model** used for each file automatically.
* **Extracts model-specific** summary results efficiently.
* **Saves all extracted results** into a single Excel workbook.
* **Organizes results** into separate sheets by HyPhy model.
* **Highlights significant results** automatically (e.g., p-value < 0.05).
* **Shows parsing errors** or skipped files clearly in the log console.

**Input**
Use the final `.json` output files generated by the HyPhy Execution module:
```text
GeneName_aln_rec_v1_MMDD_BUSTED.json
GeneName_aln_rec_v1_MMDD_RELAX.json
```

**Output**
The module generates a single organized Excel workbook:
```text
HyPhy_results_summary_MMDD.xlsx
```

---

## Supported HyPhy Models
Currently supported models across all modules include:
* BUSTED
* aBSREL
* RELAX
* FEL
* MEME
* FUBAR
* SLAC

---

## Dependencies
To use the full HYphlow pipeline, ensure the following dependencies are installed.

**For HyPhy Execution:**
The HyPhy engine must be installed and accessible from your command line.
```bash
conda install -c bioconda hyphy
hyphy --version
```

**For Python Modules:**
The following Python packages are required to run GUI components, parse trees, align data, and generate Excel files.
```bash
pip install pandas biopython ete3 rapidfuzz taxopy xlsxwriter PyQt5
```
