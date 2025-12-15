
#include <stdlib.h>

extern "C" {
    void* __cxa_allocate_exception(size_t) {
        abort();
    }

    void __cxa_throw(void *, void *, void (*)(void *)) {
        abort();
    }
}

