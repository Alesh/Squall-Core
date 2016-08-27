#include <csignal>
#include <iostream>
#include <squall/Dispatcher.hxx>
#include <squall/Loop.hxx>
#include <string>

using std::string;
using squall::Loop;
using squall::Event;
using Dispatcher = squall::Dispatcher<string>;


int main(int argc, char const *argv[]) {

    Dispatcher dispatcher(
        [&dispatcher](const string &target, int revents, const void *payload) {
            if (revents == Event::Timer) {
                std::cout << "Hello, " << target << "! (" << revents << ")" << std::endl;
                return true;
            } else {
                if (revents == Event::Cleanup)
                    std::cout << "Bye, " << target << "! (" << revents << ")" << std::endl;
                else
                    std::cout << "\nGot " << target << "! (" << revents << ")" << std::endl;
                Loop::current().stop();
                return false;
            }
        },
        Loop::current());

    dispatcher.watch_timer(string("Alesh"), 1.0);
    dispatcher.watch_timer(string("World"), 3.0);
    dispatcher.watch_signal(string("SIGINT"), SIGINT);
    Loop::current().start();
    return 0;
}