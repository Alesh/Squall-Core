# Squall #

The Squall is a framework which implements the cooperative multitasking
based on event-driven switching async/await coroutines.


#### This is contains several components (modules) ####

 * **_squall** -- Low-level event dispatcher and I/O autobuffer designed
   for use with a callback functions.
 * **squall.abc** -- Abstract base classes.
 * **squall.coroutine** -- Basic awaitables and event dispatcher designed
   for use with an **async/await** coroutines described in the PEP492.
 * **squall.network** -- Implementation of async network primitives based
   on **async/await** coroutines.
