### align exome seq files and call with cnvnator

THREADS=64
JAVA='~/jdk1.8.0_92/bin/java '
CNVNATOR='bin/CNVnator-master/cnvnator '
BWA='~/bin/bwa '
SAMTOOLS='bin/CNVnator-master/samtools/samtools '
GAPFILE='centromers.telomers.txt'

MIN_CNV_LENGTH=50000
PVAL_THRESHOLD=0.05
QVAL_THRESHOLD=0.5
BIN_SIZE=[20, 100, 300]

rule all:
	#input: 'cnvs/FTD_P1_E02-35794035/FTD-P1-E02_S15_L003_L004.cnv'
	#input: 'cnvs/FTD_P1_F04-35810021/FTD-P1-F04_S16_L003_L004.cnv'	
	input: expand('filtered_cnvs/FTD_P1_E09-35796034/FTD-P1-E09_S7_L001_L002_bin{bin_size}_length' + str(MIN_CNV_LENGTH) +'.cnv', bin_size=BIN_SIZE)

	
rule filter_CNVs:
	""" filter cnvs for: cnv length, e-val threshold, and q-value. see >>> cnv calling at https://github.com/abyzovlab/CNVnator/blob/master/README"""
	input: 'gapsRemoved/{sample}/{file}_L{laneA}_L{laneB}_bin{bin_size}.cnv'
	output: 'filtered_cnvs/{sample}/{file}_L{laneA}_L{laneB}_bin{bin_size}_length{length}.cnv'
	params: pval=PVAL_THRESHOLD, qval=QVAL_THRESHOLD
	shell: """TOTAL=`wc -l < {input}`;
		awk '{{ if ($9 <= 0 && $9 < {params.qval} && $3 >= {wildcards.length} && $5 <= {params.pval} && $6 <= {params.pval} && $7 < {params.pval} && $8 < {params.pval}) print; }}' {input} | sort -g -k5,6 > {output}; FILTERED=`wc -l < {output}`; echo $FILTERED / $TOTAL cnvs left"""

rule removeGaps:
	input: 'cnvs/{sample}/{file}_L{laneA}_L{laneB}_bin{bin_size}.cnv'
	output: temp('gapsRemoved/{sample}/{file}_L{laneA}_L{laneB}_bin{bin_size}.cnv')
	params: gapfile=GAPFILE
	run: 	
		def getTuple(loc):
			loc = loc.strip()
			[chr, interval] = loc.split(':')
			[start, end] = interval.split('-')
			return chr, start, end
		
		file = open(GAPFILE, 'r')
		map = {}
		for line in file.readlines():
			chr, start, end = getTuple(line)
			if chr not in map:
				map[chr] = []
			map[chr].append([start,end])
		
		file.close()
		
		lines=0
		totalGapCalls=0
		written=0
		file = open(input[0], 'r')
		outfile = open(output[0], 'w')
		for line in file.readlines():
			location = line.split('\t')[1]
			chr, start, end = getTuple(location)
			
			if chr in map:
				gapFlag = False
				for locs in map[chr]:
					gapStart = locs[0]
					gapEnd = locs[1]
					if (start <= gapEnd and not end <= gapStart) or (end >= gapEnd and not start >= gapStart): 
						#print(chr, start, end, 'locus in gapped region')
						gapFlag = True					
				if not gapFlag:
					outfile.write(line)
					written += 1
				else:
					totalGapCalls += 1
			lines += 1
		file.close()
		outfile.close()
		
		print("%d from %d calls removed due to centromere/telomere overlaps. %d cnv calls remaining" % (totalGapCalls, lines, written))
					
	
	
rule cnv_calling:
	""" call the cnvs with CNVnator """
	input: log='logs/{sample}/partition.{file}_L{laneA}_L{laneB}_bin{bin_size}.log', 		
	output: 'cnvs/{sample}/{file}_L{laneA}_L{laneB}_bin{bin_size}.cnv'
	params: bin_size=BIN_SIZE, root='root/{sample}/{file}_L{laneA}_L{laneB}.root'
	shell: CNVNATOR + "-root {params.root} -call {params.bin_size} > {output}"
	
rule rd_signal_partitioning:
	""" partitioning step, this takes a while """
	input:  log='logs/{sample}/statistics.{file}_L{laneA}_L{laneB}_bin{bin_size}.log'
	output: log='logs/{sample}/partition.{file}_L{laneA}_L{laneB}_bin{bin_size}.log'
	params: bin_size=BIN_SIZE, root='root/{sample}/{file}_L{laneA}_L{laneB}.root',
	shell: CNVNATOR + "-root {params.root} -partition {params.bin_size} > {output.log}"

rule statistics:
	""" create statistics on the root"""
	input: log='logs/{sample}/histogram.{file}_L{laneA}_L{laneB}_bin{bin_size}.log'	
	output: log='logs/{sample}/statistics.{file}_L{laneA}_L{laneB}_bin{bin_size}.log'
	params: bin_size=BIN_SIZE, root='root/{sample}/{file}_L{laneA}_L{laneB}.root'
	shell: CNVNATOR + "-root {params.root} -genome hg18 -stat {params.bin_size} > {output.log}"

rule generate_histogram:
	""" create histogram, as the original files are modified, further requirements for snakemake are the logs from streaming std into files """
	input: log='logs/{sample}/extraction.{file}_L{laneA}_L{laneB}.log', reference="indexed/chr"
	output: log='logs/{sample}/histogram.{file}_L{laneA}_L{laneB}_bin{bin_size}.log'
	params: bin_size=BIN_SIZE, root='root/{sample}/{file}_L{laneA}_L{laneB}.root'
	shell: CNVNATOR + "-root {params.root} -his {params.bin_size} -d {input.reference} > {output.log}"
	
rule extractReadMapping:
	""" use root to generate a tree """
	input: bam='bam/{sample}/{file}_L{laneA}_L{laneB}.bam'
	output: root='root/{sample}/{file}_L{laneA}_L{laneB}.root', log='logs/{sample}/extraction.{file}_L{laneA}_L{laneB}.log'
	shell: CNVNATOR + "-root {output.root} -tree {input.bam} -unique > {output.log}"
	
### still incomplete, have to fix the subpipeline which is limited to hg19 and hg38
rule runPennCNV:
	"""use PennCNV-seq to create intensity files and call cnvs"""
	input: bam='bam/{sample}/{file}_L{laneA}_L{laneB}.bam', reference='indexed/hg18.fa'
	output: 'rawcnv/{sample}/{file}_L{laneA}_L{laneB}.rawcnv'
	shell: "./bin/PennCNV-Seq-master/penncnv-seq-hg18.sh ~/CNV/PennCNV-1.0.4 ~/bin/PennCNV-Seq-master/reference hg18 EUR {input.reference} {input.bam}; touch {output}"

rule convert_and_sort_sam_to_bam:
	""" samtools sam to bam conversion; piping into a sorted bam """
	input: sam='sam/{sample}/{file}_L{laneA}_L{laneB}.sam'
	output: bam='bam/{sample}/{file}_L{laneA}_L{laneB}.bam'#, bai='bam/{sample}/{file}_L{laneA}_L{laneB}.bai'
	params: bam='bam/{sample}/{file}_L{laneA}_L{laneB}'
	shell: SAMTOOLS + 'view -bS {input.sam} | samtools sort - {params.bam}'

### Defect, doesnt work with the output created by bwa	
#rule convert_sam_to_bam:
#	""" use picard to create bam file from sam"""
#	input: sam='sam/{sample}/{file}_L{laneA}_L{laneB}.sam'
#	output: bam='bam/{sample}/{file}_L{laneA}_L{laneB}.bam'
#	shell: JAVA + """-Xmx4g -Djava.io.tmpdir=/tmp \
#					-jar bin/picard.jar SortSam \
#					SO=coordinate \
#					INPUT={input.sam} \
#					OUTPUT={output.bam} \
#					VALIDATION_STRINGENCY=LENIENT \
#					CREATE_INDEX=true"""
	
rule pairedEnd:
	""" make a paired end sam file from forward and reverse strands"""
	input: fwd_sai='aligned/{sample}/{file}_L{laneA}_L{laneB}_R1.sai', rev_sai='aligned/{sample}/{file}_L{laneA}_L{laneB}_R2.sai', fwd_fastq='merged/{sample}/{file}_L{laneA}_L{laneB}_R1.fastq.gz', rev_fastq='merged/{sample}/{file}_L{laneA}_L{laneB}_R2.fastq.gz'
	output: sam=temp('sam/{sample}/{file}_L{laneA}_L{laneB}.sam')
	shell: BWA + """sampe -f {output.sam} -r '@RG\\tID:{wildcards.sample}_{wildcards.file}_L{wildcards.laneA}_L{wildcards.laneB}\\tLB:{wildcards.sample}_{wildcards.file}_L{wildcards.laneA}_L{wildcards.laneB}\\tSM:{wildcards.sample}_{wildcards.file}_L{wildcards.laneA}_L{wildcards.laneB}\\tPL:ILLUMINA' indexed/hg18 {input.fwd_sai} {input.rev_sai} {input.fwd_fastq} {input.rev_fastq}"""
	
rule alignSamples:
	"""align fastq samples to indexed reference"""
	input: fastq='merged/{sample}/{file}_L{laneA}_L{laneB}_R{R}.fastq.gz', index='indexed/hg18.ann'
	params: index='indexed/hg18'
	output: sai='aligned/{sample}/{file}_L{laneA}_L{laneB}_R{R}.sai'
	threads: THREADS
	shell: BWA + 'aln -t {threads} -f {output.sai} {params.index} {input.fastq}'

rule merge:
	""" Merge the lanes into single fastq """
	input: laneA='fastq/{sample}/{file}_L{laneA}_R{R}_001.fastq.gz', laneB='fastq/{sample}/{file}_L{laneB}_R{R}_001.fastq.gz'
	output: temp('merged/{sample}/{file}_L{laneA}_L{laneB}_R{R}.fastq.gz')
	shell: 'cat {input.laneA} {input.laneB} > {output}'

### gzip doesnt need this, actually	
#rule gunzip:
#	input: gz='fastq/{sample}/{file}_L{lane}_R{R}_001.fastq.gz'
#	output: temp(fastq='fastq/{sample}/{file}_L{laneA}_R{R}_001.fastq')
#	shell: "gunzip -c {input.gz} > {output.fastq}
	
rule index:
	"""index reference (takes a while) """
	input: 'indexed/hg18.fa'
	output: 'indexed/hg18.pac', 'indexed/hg18.amb', 'indexed/hg18.ann'
	shell: BWA + ' index -a bwtsw -p indexed/hg18 indexed/hg18.fa'

rule makeFa:
	"""merge reference (http://hgdownload.cse.ucsc.edu/goldenPath/hg18/bigZips/chromFa.zip) to single fasta """
	input: expand('chromFa/chr{chr}.fa', chr=list(range(1,22)) + ['X', 'Y','M'])
	output: 'indexed/hg18.fa'
	shell: 'cat {input} > {output}'