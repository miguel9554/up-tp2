# LibreLane floorplan and placement flows, executed inside the container via
# run.sh. They start from the netlist synthesized in TP1: nothing here runs
# synthesis again. Every run also generates reports in <run>/reports/*.md.
#
#   make import-tp1 TP1_RUN=<dir>      # import the netlist of a TP1 run (its directory)
#   make footprint AREA=2.7e6 ASPECT=1 # footprint: die of AREA µm² (height/width ASPECT) and I/O pins
#   make floorplan                     # floorplan: rows, macros, taps, power grid
#   make place                         # floorplan + placement + post-placement STA
#   make place NAME=center             # same, run tagged pl_center_<timestamp>
#   make gui-footprint                 # open the footprint (die and pins) in the OpenROAD GUI
#   make gui                           # open the latest run in the OpenROAD GUI
#   make gui RUN=<run> STEP=10         # open a given run, as it was after a given step
#   make compare                       # compare every placement run
#   make report                        # (re)generate reports of the latest run
#   make shell                         # interactive shell in the container
#   make clean                         # remove runs of DESIGN

DESIGN ?= ibex
TP1_RUN ?=
AREA    ?=
ASPECT  ?= 1
NAME   ?=
RUN    ?=
STEP   ?=
RUNS   ?=

DESIGN_DIR := designs/$(DESIGN)
CONFIG     := $(DESIGN_DIR)/config.json
STATE      := $(DESIGN_DIR)/tp1/state.json
FOOTPRINT  := $(DESIGN_DIR)/footprint.def
STAMP      := $(shell date +%Y-%m-%d_%H-%M-%S)
RUNSH      := ./run.sh

LAST_RUN = $(notdir $(patsubst %/resolved.json,%,$(lastword \
             $(shell ls -1tr $(DESIGN_DIR)/runs/*/resolved.json 2>/dev/null))))
GUI_RUN  = $(or $(RUN),$(LAST_RUN))

# $(call FLOW,<tag prefix>,<last step>)
TAG  = $(1)$(if $(NAME),_$(NAME))_$(STAMP)
FLOW = $(RUNSH) librelane --design-dir $(DESIGN_DIR) --run-tag $(TAG) \
         --with-initial-state $(STATE) --from OpenROAD.Floorplan --to $(2) $(CONFIG) && \
       $(RUNSH) python3 scripts/report.py $(DESIGN_DIR)/runs/$(TAG)

.PHONY: import-tp1 footprint floorplan place gui-footprint gui compare report shell clean

import-tp1:
	@[ -n "$(TP1_RUN)" ] || { echo "error: give the TP1 run directory: make import-tp1 TP1_RUN=<dir>"; exit 1; }
	@[ -d "$(TP1_RUN)" ] || { echo "error: $(TP1_RUN) does not exist"; exit 1; }
	TP1_RUN=$(TP1_RUN) $(RUNSH) python3 scripts/import_tp1.py /tp1_run $(DESIGN) $(abspath $(TP1_RUN))

$(STATE):
	@echo "error: the TP1 netlist was not imported yet. Run: make import-tp1 TP1_RUN=<TP1 run dir>"
	@exit 1

$(FOOTPRINT):
	@echo "error: there is no footprint yet. Run: make footprint AREA=<die area in µm²> ASPECT=<height/width>"
	@exit 1

footprint: $(STATE)
	@[ -n "$(AREA)" ] || { echo "error: give the die area: make footprint AREA=<µm²> ASPECT=<height/width>"; exit 1; }
	$(RUNSH) python3 scripts/footprint.py $(DESIGN) $(AREA) $(ASPECT)

floorplan: $(STATE) $(FOOTPRINT)
	$(call FLOW,fp,Odb.RemovePDNObstructions)

# OpenROAD.STAMidPNR-1 is the STA added right after detailed placement
# (see "meta" in config.json).
place: $(STATE) $(FOOTPRINT)
	$(call FLOW,pl,OpenROAD.STAMidPNR-1)

# Checks there is a display and lets the container (same uid) use it.
define X11
	@[ -n "$$DISPLAY" ] || { echo "error: DISPLAY is not set: run this from a graphical session"; exit 1; }
	@xhost +SI:localuser:$$(id -un) >/dev/null 2>&1 || \
	  echo "warning: xhost failed; if the GUI does not open, install x11-xserver-utils"
endef

gui-footprint: $(FOOTPRINT)
	$(X11)
	$(RUNSH) python3 scripts/gui_footprint.py $(DESIGN)

gui:
	@[ -n "$(GUI_RUN)" ] || { echo "error: no runs yet: run make floorplan or make place"; exit 1; }
	$(X11)
	$(RUNSH) librelane --design-dir $(DESIGN_DIR) --run-tag $(GUI_RUN) --flow OpenInOpenROAD \
	  $(if $(STEP),--with-initial-state $(firstword $(wildcard $(DESIGN_DIR)/runs/$(GUI_RUN)/$(STEP)-*/state_out.json))) \
	  $(CONFIG)

compare:
	$(RUNSH) python3 scripts/compare.py $(DESIGN_DIR) $(RUNS)

report:
	$(RUNSH) python3 scripts/report.py $(DESIGN_DIR)

shell:
	$(RUNSH)

clean:
	rm -rf $(DESIGN_DIR)/runs
