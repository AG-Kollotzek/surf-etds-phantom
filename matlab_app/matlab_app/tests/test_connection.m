function tests = test_connection
    tests = functiontests(localfunctions);
end

function testDummy(t)
    verifyTrue(t, true);
end
