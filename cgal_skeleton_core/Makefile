
CXX ?= clang++

BUILDDIR ?= build
CACHEDIR ?= cache

CGAL ?= CGAL-6.1
CGAL_URL ?= https://github.com/CGAL/cgal/releases/download/v6.1/CGAL-6.1-library.tar.xz

BOOST ?= boost_1_90_0
BOOST_URL ?= https://archives.boost.io/release/1.90.0/source/boost_1_90_0.tar.gz

WASI_SDK_URL ?= https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-29/wasi-sdk-29.0-x86_64-linux.tar.gz
WASI_SDK ?= $(CACHEDIR)/wasi-sdk-29.0-x86_64-linux

SOURCES := \
	skeleton_wrapper.cpp

WASI_SOURCES := \
	$(SOURCES) \
	exception_stubs.cpp \

INCLUDES := -I$(CACHEDIR)/$(CGAL)/include -I$(CACHEDIR)/$(BOOST)
CXXFLAGS := -std=c++20 -g -Wall -Wextra -O2 
WASI_CXXFLAGS := -DCGAL_ALWAYS_ROUND_TO_NEAREST -DCGAL_CORE_USE_BOOST_BACKEND -DCGAL_DISABLE_GMP -DCGAL_USE_BOOST_MP -DFE_UPWARD=FE_TONEAREST -D_WASI_EMULATED_PROCESS_CLOCKS $(CXXFLAGS)
LDFLAGS :=
HOST_LDFLAGS := $(LDFLAGS) -lgmp -lmpfr
WASI_LDFLAGS := $(LDFLAGS) -lwasi-emulated-process-clocks 

WASI_CXX ?= $(WASI_SDK)/bin/clang++


BINARY := skeleton

all: $(BUILDDIR)/$(BINARY) wasm

.PHONY: wasm
wasm: $(BUILDDIR)/$(BINARY).wasm

$(BUILDDIR)/$(BINARY): $(SOURCES)
	$(CXX) $(CXXFLAGS) $(HOST_LDFLAGS) -o $@ $^

$(WASI_SDK):
	mkdir -p $(dir $@)
	cd $(dir $@); curl -L ${WASI_SDK_URL} | tar xzf -

$(CACHEDIR)/$(BOOST):
	cd $(dir $@); curl -L ${BOOST_URL} | tar xzf -

$(CACHEDIR)/$(CGAL):
	cd $(dir $@); curl -L ${CGAL_URL} | tar xJf -

$(BUILDDIR)/wasi/%.o: %.cpp $(WASI_SDK) 
	@mkdir -p $(dir $@) 
	$(WASI_CXX) -c $(WASI_CXXFLAGS) $(INCLUDES) -o $@ $<

$(BUILDDIR)/$(BINARY).wasm: $(patsubst %.cpp,$(BUILDDIR)/wasi/%.o,$(WASI_SOURCES))
	@mkdir -p $(dir $@)
	$(WASI_CXX) $(WASI_LDFLAGS) -o $@ $^

.PHONY: clean
clean:
	rm -rf $(BUILDDIR)

.PHONY: mrproper
mrproper: clean
	rm -rf $(CACHEDIR)
